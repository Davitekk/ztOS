// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * The cameras behind Qualcomm's camss, through V4L2: raw Bayer with no ISP, and a media
 * graph to set up first. The device's ztcamera-route script does that part and says what
 * the frames look like, so nothing here knows a particular phone.
 *
 * The frame is made on the CPU from blocks of the sensor's 2x2 cells, averaged: black level,
 * blending over frames, hot pixels, white balance, colour noise, a colour matrix, sRGB. No
 * demosaic, so a photo is half the sensor's width and height. Exposure and analogue gain are
 * the sensor's, and white balance the grey world's unless a dial says otherwise. Focus does
 * not move: the lens driver is not there yet.
 * Included by ztcamera.c.
 */
#include <stddef.h>

#define CAMSS_ROUTE	"ztcamera-route"
#define CAMSS_BUFS	4
#define CAMSS_AE_TARGET	0.16	/* of the sensor's range, green, in the linear */
#define CAMSS_SLOWEST_FPS 15	/* how far the dark may slow the preview down */
#define CAMSS_DIGITAL_MAX 8.0	/* past the sensor's limits, in the dark: noisy, but a picture */
#define CAMSS_BLEND	3	/* how many frames before weigh against this one */
#define CAMSS_PHOTO_FRAMES 3	/* averaged into a photo */

enum camss_cam { CAMSS_REAR, CAMSS_FRONT };

static struct {
	enum camss_cam cam;
	char video[64], subdev[64], fmt[8], order[8];
	int w, h, pitch, bits, rotate, mirror, black, white, gain_base, line;
	int fd, sub;
	struct { void *start; size_t len; } buf[CAMSS_BUFS];
	int nbuf;
	int exposure, exposure_max, gain, gain_max, gain_step;
	int exposure_base, blank_base, blank, rate;
	int line_preview;	/* a row's time at the preview's blanking */
	double wb_r, wb_b, digital;
	unsigned seq;
	struct { int exposure, gain; double digital, wb_r, wb_b; } saved[2];
	/* the worker */
	pthread_t thread;
	pthread_mutex_t lock;
	pthread_cond_t wake;
	bool worker, quit, collected;
	int held, done_fd;
	struct v4l2_buffer held_buf;
	cairo_surface_t *back;
	int r_at, g0_at, g1_at, b_at;	/* the colours' places in the 2x2 cell */
} cs = { .fd = -1, .sub = -1, .wb_r = 1.6, .wb_b = 1.6, .digital = 1, .held = -1, .done_fd = -1,
	.lock = PTHREAD_MUTEX_INITIALIZER, .wake = PTHREAD_COND_INITIALIZER };

/* What a camera's ISP would do, on the CPU, on a block of the sensor's cells per pixel. */
struct camss_planes {
	int w, h, frames;
	int16_t *r, *g, *b;		/* linear, above black, 16 times the sensor's 10 bits */
	int32_t *cr, *cb, *line;	/* the chroma smoothing's working space */
};

static struct camss_planes cs_preview;

static bool camss_available(void) {
	return access("/dev/media0", R_OK | W_OK) == 0 &&
		(access("/usr/local/bin/" CAMSS_ROUTE, X_OK) == 0 || access("/usr/bin/" CAMSS_ROUTE, X_OK) == 0);
}

static bool camss_route(const char *mode) {
	char cmd[96], line[128];
	snprintf(cmd, sizeof(cmd), CAMSS_ROUTE " %s %s 2>/dev/null",
		cs.cam == CAMSS_REAR ? "rear" : "front", mode);
	cs.video[0] = cs.subdev[0] = 0;
	cs.w = cs.h = 0;
	FILE *p = popen(cmd, "r");
	if (!p) {
		return false;
	}
	while (fgets(line, sizeof(line), p)) {
		char *v = strchr(line, '=');
		if (!v) {
			continue;
		}
		*v++ = 0;
		v[strcspn(v, "\n")] = 0;
		if (!strcmp(line, "video")) snprintf(cs.video, sizeof(cs.video), "%s", v);
		else if (!strcmp(line, "subdev")) snprintf(cs.subdev, sizeof(cs.subdev), "%s", v);
		else if (!strcmp(line, "fmt")) snprintf(cs.fmt, sizeof(cs.fmt), "%s", v);
		else if (!strcmp(line, "order")) snprintf(cs.order, sizeof(cs.order), "%s", v);
		else if (!strcmp(line, "w")) cs.w = atoi(v);
		else if (!strcmp(line, "h")) cs.h = atoi(v);
		else if (!strcmp(line, "pitch")) cs.pitch = atoi(v);
		else if (!strcmp(line, "bits")) cs.bits = atoi(v);
		else if (!strcmp(line, "rotate")) cs.rotate = atoi(v);
		else if (!strcmp(line, "mirror")) cs.mirror = atoi(v);
		else if (!strcmp(line, "black")) cs.black = atoi(v);
		else if (!strcmp(line, "white")) cs.white = atoi(v);
		else if (!strcmp(line, "gain_base")) cs.gain_base = atoi(v);
		else if (!strcmp(line, "line")) cs.line = atoi(v);
		else if (!strcmp(line, "rate")) cs.rate = atoi(v);
	}
	/* with SIGCHLD ignored, pclose cannot know how it ended: -1, ECHILD, and what it said
	 * has to do */
	int status = pclose(p);
	if ((status != 0 && !(status == -1 && errno == ECHILD)) || !cs.video[0] || !cs.subdev[0] ||
			cs.w < 16 || cs.h < 16 || (cs.bits != 10 && cs.bits != 14) ||
			strlen(cs.order) != 4 || strlen(cs.fmt) != 4) {
		fprintf(stderr, "ztcamera: " CAMSS_ROUTE " %s: status %d, %dx%d\n", mode, status, cs.w, cs.h);
		return false;
	}
	const char *r = strchr(cs.order, 'R'), *b = strchr(cs.order, 'B');
	const char *g0 = strchr(cs.order, 'G'), *g1 = strrchr(cs.order, 'G');
	if (!r || !b || !g0 || g0 == g1) {
		return false;
	}
	cs.r_at = r - cs.order;
	cs.b_at = b - cs.order;
	cs.g0_at = g0 - cs.order;
	cs.g1_at = g1 - cs.order;
	return true;
}

static void camss_set_ctrl(uint32_t id, int value) {
	struct v4l2_control c = { .id = id, .value = value };
	if (cs.sub >= 0) {
		ioctl(cs.sub, VIDIOC_S_CTRL, &c);
	}
}

static int camss_ctrl_range(uint32_t id, int *step) {
	struct v4l2_queryctrl q = { .id = id };
	if (cs.sub < 0 || ioctl(cs.sub, VIDIOC_QUERYCTRL, &q) != 0) {
		return 0;
	}
	if (step) {
		*step = q.step > 0 ? q.step : 1;
	}
	return q.maximum;
}

static void camss_worker_stop(void);

static void camss_stream_stop(void) {
	camss_worker_stop();
	if (cs.fd >= 0) {
		enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
		ioctl(cs.fd, VIDIOC_STREAMOFF, &type);
		for (int i = 0; i < cs.nbuf; i++) {
			munmap(cs.buf[i].start, cs.buf[i].len);
		}
		cs.nbuf = 0;
		close(cs.fd);
		cs.fd = -1;
	}
	if (cs.sub >= 0) {
		close(cs.sub);
		cs.sub = -1;
	}
}

static bool camss_stream_start(void) {
	cs.sub = open(cs.subdev, O_RDWR | O_CLOEXEC);
	cs.fd = open(cs.video, O_RDWR | O_NONBLOCK | O_CLOEXEC);
	if (cs.fd < 0 || cs.sub < 0) {
		camss_stream_stop();
		return false;
	}
	struct v4l2_format f;
	memset(&f, 0, sizeof(f));
	f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	f.fmt.pix_mp.width = cs.w;
	f.fmt.pix_mp.height = cs.h;
	f.fmt.pix_mp.pixelformat = v4l2_fourcc(cs.fmt[0], cs.fmt[1], cs.fmt[2], cs.fmt[3]);
	f.fmt.pix_mp.field = V4L2_FIELD_NONE;
	f.fmt.pix_mp.num_planes = 1;
	if (ioctl(cs.fd, VIDIOC_S_FMT, &f) != 0) {
		camss_stream_stop();
		return false;
	}
	/* The front sensor sends 8 more pixels a row than its format says, and the VFE writes them
	 * all, past the end of a buffer of the format's size: buffers for what really comes. */
	struct v4l2_create_buffers req;
	memset(&req, 0, sizeof(req));
	req.count = CAMSS_BUFS;
	req.memory = V4L2_MEMORY_MMAP;
	req.format = f;
	unsigned need = (unsigned)cs.pitch * cs.h + 4096;
	if (req.format.fmt.pix_mp.plane_fmt[0].sizeimage < need) {
		req.format.fmt.pix_mp.plane_fmt[0].sizeimage = need;
	}
	if (ioctl(cs.fd, VIDIOC_CREATE_BUFS, &req) != 0 || req.count < 2 || req.count > CAMSS_BUFS) {
		camss_stream_stop();
		return false;
	}
	for (unsigned i = 0; i < req.count; i++) {
		struct v4l2_plane plane;
		struct v4l2_buffer b;
		memset(&plane, 0, sizeof(plane));
		memset(&b, 0, sizeof(b));
		b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
		b.memory = V4L2_MEMORY_MMAP;
		b.index = i;
		b.m.planes = &plane;
		b.length = 1;
		if (ioctl(cs.fd, VIDIOC_QUERYBUF, &b) != 0) {
			camss_stream_stop();
			return false;
		}
		void *p = mmap(NULL, plane.length, PROT_READ, MAP_SHARED, cs.fd, plane.m.mem_offset);
		if (p == MAP_FAILED) {
			camss_stream_stop();
			return false;
		}
		cs.buf[i].start = p;
		cs.buf[i].len = plane.length;
		cs.nbuf = i + 1;
		if (ioctl(cs.fd, VIDIOC_QBUF, &b) != 0) {
			camss_stream_stop();
			return false;
		}
	}
	/* the shortest frame first: what exposure it allows is the base of the ladder */
	struct v4l2_queryctrl blank = { .id = V4L2_CID_VBLANK };
	cs.blank_base = ioctl(cs.sub, VIDIOC_QUERYCTRL, &blank) == 0 ? blank.minimum : 0;
	camss_set_ctrl(V4L2_CID_VBLANK, cs.blank_base);
	cs.exposure_base = camss_ctrl_range(V4L2_CID_EXPOSURE, NULL);
	cs.blank = cs.blank_base;
	if (cs.exposure > cs.exposure_base) {
		cs.blank += cs.exposure - cs.exposure_base;
		camss_set_ctrl(V4L2_CID_VBLANK, cs.blank);
	}
	cs.exposure_max = camss_ctrl_range(V4L2_CID_EXPOSURE, NULL);
	cs.gain_max = camss_ctrl_range(V4L2_CID_ANALOGUE_GAIN, &cs.gain_step);
	camss_set_ctrl(V4L2_CID_EXPOSURE, cs.exposure > cs.exposure_max ? cs.exposure_max : cs.exposure);
	camss_set_ctrl(V4L2_CID_ANALOGUE_GAIN, cs.gain);
	cs_preview.frames = 0;
	enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	if (ioctl(cs.fd, VIDIOC_STREAMON, &type) != 0) {
		camss_stream_stop();
		return false;
	}
	return true;
}

static void camss_close(void) {
	camss_stream_stop();
}

/* The sizes of what comes out of a frame, upright: cells across and down the sensor */
static void camss_cells(int full, int *step_x, int *step_y, int *cols, int *rows) {
	int sx = full ? 2 : (cs.w / 640 < 2 ? 2 : (cs.w / 640) & ~1);
	int sy = full ? 2 : (cs.h / 480 < 2 ? 2 : (cs.h / 480) & ~1);
	*step_x = sx;
	*step_y = sy;
	*cols = (cs.w - 1) / sx;
	*rows = (cs.h - 1) / sy;
}

/* Exposure, then a little gain, then a longer frame in the dark, then gain: a slower picture
 * is better than a noisier one, down to CAMSS_SLOWEST_FPS. */
static void camss_expose(double green, double clipped) {
	double target = CAMSS_AE_TARGET * (cs.white - cs.black);
	if (clipped > 0.04) {
		target *= 0.7;	/* a lamp in the picture: keep what is around it */
	}
	double r = green > 0.5 ? target / green : 3;
	int base = cs.gain_base > 0 ? cs.gain_base : 256;
	double again = (double)base / (base - cs.gain);
	double top = (double)base / (base - cs.gain_max);
	/* what the sensor cannot reach is made up here, slowly, so it does not pump */
	{
		/* Once it is in use the sensor holds still and this alone follows the light: with
		 * both moving, the gain went up and down between steps and the picture pulsed. */
		bool limit = again >= top * 0.95 && cs.exposure >= cs.exposure_base && (r > 1 || cs.digital > 1.02);
		double d = limit ? r : 1;	/* r is against the raw, before this gain */
		d = d > CAMSS_DIGITAL_MAX ? CAMSS_DIGITAL_MAX : d < 1 ? 1 : d;
		cs.digital += (d - cs.digital) * 0.25;
		if (cs.digital > 1.02) {
			return;
		}
		cs.digital = 1;
	}
	if ((r > 0.88 && r < 1.14) || cs.exposure_base <= 0) {
		return;
	}
	r = r > 2.5 ? 2.5 : r < 0.5 ? 0.5 : r;
	double want = cs.exposure * again * r;
	int longest = cs.line > 0 && cs.rate > 0 ? (int)((double)cs.rate / CAMSS_SLOWEST_FPS / cs.line) : cs.exposure_base;
	if (longest < cs.exposure_base) {
		longest = cs.exposure_base;
	}
	int e;
	if (want <= cs.exposure_base) {
		e = want < 4 ? 4 : (int)want;
	} else if (want <= cs.exposure_base * 2.0) {
		e = cs.exposure_base;
	} else {
		e = (int)(want / 2);
		e = e > longest ? longest : e < cs.exposure_base ? cs.exposure_base : e;
	}
	double a = want / e;
	a = a > top ? top : a < 1 ? 1 : a;
	/* Upwards to the sensor's next step: the front's run 8x then 16x, and rounding down stayed
	 * at 8x, never reaching the top where digital gain takes over, so the dark stayed black */
	int g = (int)(base - base / a), gain_step = cs.gain_step > 0 ? cs.gain_step : 1;
	g = (g + gain_step - 1) / gain_step * gain_step;
	g = g > cs.gain_max ? cs.gain_max : g;
	int blank = cs.blank_base + (e > cs.exposure_base ? e - cs.exposure_base : 0);
	/* the frame grows before the exposure does, and shrinks after */
	if (blank > cs.blank) {
		cs.blank = blank;
		camss_set_ctrl(V4L2_CID_VBLANK, blank);
	}
	if (e != cs.exposure) {
		cs.exposure = e;
		camss_set_ctrl(V4L2_CID_EXPOSURE, e);
	}
	if (g != cs.gain) {
		cs.gain = g;
		camss_set_ctrl(V4L2_CID_ANALOGUE_GAIN, g);
	}
	if (blank < cs.blank) {
		cs.blank = blank;
		camss_set_ctrl(V4L2_CID_VBLANK, blank);
	}
}

static void camss_planes_free(struct camss_planes *p) {
	free(p->r);
	free(p->g);
	free(p->b);
	free(p->cr);
	free(p->cb);
	free(p->line);
	memset(p, 0, sizeof(*p));
}

static bool camss_planes_size(struct camss_planes *p, int w, int h) {
	if (p->w == w && p->h == h && p->r) {
		return true;
	}
	camss_planes_free(p);
	size_t n = (size_t)w * h;
	p->r = malloc(n * sizeof(int16_t));
	p->g = malloc(n * sizeof(int16_t));
	p->b = malloc(n * sizeof(int16_t));
	p->cr = malloc(n * sizeof(int32_t));
	p->cb = malloc(n * sizeof(int32_t));
	p->line = malloc(((size_t)(w > h ? w : h) + 16) * sizeof(int32_t));
	if (!p->r || !p->g || !p->b || !p->cr || !p->cb || !p->line) {
		camss_planes_free(p);
		return false;
	}
	p->w = w;
	p->h = h;
	p->frames = 0;
	return true;
}

/* A row of the sensor's packed pixels, as numbers: faster a group at a time, and the buffers
 * are write-combined, so it is copied out first. */
static void camss_unpack(const uint8_t *in, uint16_t *out, int w, uint8_t *copy) {
	memcpy(copy, in, cs.pitch);
	const uint8_t *g = copy;
	if (cs.bits == 14) {
		for (int x = 0; x < w; x += 4, g += 7) {
			out[x] = g[0] << 6 | (g[4] & 0x3f);
			out[x + 1] = g[1] << 6 | g[4] >> 6 | (g[5] & 0xf) << 2;
			out[x + 2] = g[2] << 6 | g[5] >> 4 | (g[6] & 3) << 4;
			out[x + 3] = g[3] << 6 | g[6] >> 2;
		}
	} else {
		for (int x = 0; x < w; x += 4, g += 5) {
			out[x] = g[0] << 2 | (g[4] & 3);
			out[x + 1] = g[1] << 2 | (g[4] >> 2 & 3);
			out[x + 2] = g[2] << 2 | (g[4] >> 4 & 3);
			out[x + 3] = g[3] << 2 | g[4] >> 6;
		}
	}
}

/* The block's average per colour, into the planes, and blended with the frames before where
 * nothing moved: noise falls with the frames, a moving hand stays sharp. */
static void camss_gather(const uint8_t *in, struct camss_planes *p, int sx, int sy, double *mean) {
	uint8_t *copy = malloc(cs.pitch);
	uint16_t *row0 = malloc((cs.w + 8) * sizeof(uint16_t)), *row1 = malloc((cs.w + 8) * sizeof(uint16_t));
	int32_t *sums = malloc(sizeof(int32_t) * 3 * p->w);
	if (!copy || !row0 || !row1 || !sums) {
		free(copy);
		free(row0);
		free(row1);
		free(sums);
		return;
	}
	const uint16_t *rows[2] = { row0, row1 };
	const uint16_t *at_r = rows[cs.r_at >> 1] + (cs.r_at & 1), *at_b = rows[cs.b_at >> 1] + (cs.b_at & 1);
	const uint16_t *at_g0 = rows[cs.g0_at >> 1] + (cs.g0_at & 1), *at_g1 = rows[cs.g1_at >> 1] + (cs.g1_at & 1);
	/* Reading every row costs more than this CPU has to give: one row of cells a block, and
	 * always the same one, as another each frame made the picture shimmer. */
	int cells_x = sx / 2 > 0 ? sx / 2 : 1, cells = cells_x;
	int black = cs.black * 16;
	bool first = p->frames == 0;
	int weight = p->frames < CAMSS_BLEND ? p->frames : CAMSS_BLEND;
	/* what counts as motion, above the noise: more of it in the dark */
	int moved = 48 + 8 * (cs.gain * 8 / (cs.gain_base > 0 ? cs.gain_base : 256));
	long long sum_r = 0, sum_g = 0, sum_b = 0, n = 0, bright = 0;
	int very = (cs.white - cs.black) * 16 * 9 / 10;
	for (int iy = 0; iy < p->h; iy++) {
		int16_t *pr = p->r + (size_t)iy * p->w, *pg = p->g + (size_t)iy * p->w, *pb = p->b + (size_t)iy * p->w;
		memset(sums, 0, sizeof(int32_t) * 3 * p->w);
		{
			int y = iy * sy;
			camss_unpack(in + (size_t)y * cs.pitch, row0, cs.w, copy);
			camss_unpack(in + (size_t)(y + 1) * cs.pitch, row1, cs.w, copy);
			int32_t *s = sums;
			for (int ix = 0; ix < p->w; ix++, s += 3) {
				int x = ix * sx;
				for (int cx = 0; cx < cells_x; cx++, x += 2) {
					s[0] += at_r[x];
					s[1] += at_g0[x] + at_g1[x];
					s[2] += at_b[x];
				}
			}
		}
		const int32_t *s = sums;
		for (int ix = 0; ix < p->w; ix++, s += 3) {
			int r = s[0] * 16 / cells - black;
			int g = s[1] * 8 / cells - black;
			int b = s[2] * 16 / cells - black;
			r = r < 0 ? 0 : r > 16000 ? 16000 : r;
			g = g < 0 ? 0 : g > 16000 ? 16000 : g;
			b = b < 0 ? 0 : b > 16000 ? 16000 : b;
			if (!first) {
				int d = abs(g - pg[ix]) + abs(r - pr[ix]) / 2 + abs(b - pb[ix]) / 2;
				if (d < moved + pg[ix] / 8) {
					r = (pr[ix] * weight + r) / (weight + 1);
					g = (pg[ix] * weight + g) / (weight + 1);
					b = (pb[ix] * weight + b) / (weight + 1);
				}
			}
			pr[ix] = r;
			pg[ix] = g;
			pb[ix] = b;
			if (!(ix & 7) && !(iy & 7)) {
				sum_r += r;
				sum_g += g;
				sum_b += b;
				bright += g > very;
				n++;
			}
		}
	}
	p->frames++;
	if (mean && n) {
		mean[0] = (double)sum_r / n / 16;
		mean[1] = (double)sum_g / n / 16;
		mean[2] = (double)sum_b / n / 16;
		mean[3] = (double)bright / n;
	}
	free(sums);
	free(copy);
	free(row0);
	free(row1);
}

/* A value far above both its neighbours along the row and those above and below is a stuck
 * or hot pixel, and looks like a coloured star. */
static void camss_despeckle(int16_t *v, int w, int h) {
	for (int y = 1; y < h - 1; y++) {
		int16_t *row = v + (size_t)y * w;
		for (int x = 1; x < w - 1; x++) {
			int c = row[x];
			int a = row[x - 1], b = row[x + 1], d = row[x - w], e = row[x + w];
			int top = a > b ? a : b;
			top = top > d ? top : d;
			top = top > e ? top : e;
			if (c > top + top / 2 + 64) {
				row[x] = top;
			}
		}
	}
}

/* A box over the small plane of colour, by running sums, along and then across. */
static void camss_box(int32_t *v, int w, int h, int32_t *line, int r) {
	int k = 65536 / (2 * r + 1);
	for (int y = 0; y < h; y++) {
		int32_t *row = v + (size_t)y * w;
		memcpy(line, row, sizeof(int32_t) * w);
		int sum = 0;
		for (int x = -r; x <= r; x++) {
			sum += line[x < 0 ? 0 : x];
		}
		for (int x = 0; x < w; x++) {
			row[x] = sum * k >> 16;
			int out = x - r, in = x + r + 1;
			sum += line[in >= w ? w - 1 : in] - line[out < 0 ? 0 : out];
		}
	}
	for (int x = 0; x < w; x++) {
		for (int y = 0; y < h; y++) {
			line[y] = v[(size_t)y * w + x];
		}
		int sum = 0;
		for (int y = -r; y <= r; y++) {
			sum += line[y < 0 ? 0 : y];
		}
		for (int y = 0; y < h; y++) {
			v[(size_t)y * w + x] = sum * k >> 16;
			int out = y - r, in = y + r + 1;
			sum += line[in >= h ? h - 1 : in] - line[out < 0 ? 0 : out];
		}
	}
}

/* From the planes to the picture: white balance, colour noise smoothed away on a smaller plane
 * while brightness keeps its detail, stronger colour, sRGB, and upright. Where the sensor clipped
 * its colour means nothing, and the white balance would make it magenta: no colour there, or it
 * spreads around every bright edge as a halo. */
static void camss_render(struct camss_planes *p, cairo_surface_t *surface) {
	static uint8_t gamma[4096];
	static bool gamma_ready;
	if (!gamma_ready) {
		for (int i = 0; i < 4096; i++) {
			double v = i / 4095.0;
			v = v <= 0.0031308 ? v * 12.92 : 1.055 * pow(v, 1 / 2.4) - 0.055;
			gamma[i] = (uint8_t)(v * 255 + 0.5);
		}
		gamma_ready = true;
	}
	static const double wb[5][2] = { { 1, 1 }, { 2.0, 1.25 }, { 1.8, 1.5 }, { 1.5, 1.9 }, { 1.2, 2.4 } };
	double wr = ui.ctl[0] ? wb[ui.ctl[0]][0] : cs.wb_r, wbl = ui.ctl[0] ? wb[ui.ctl[0]][1] : cs.wb_b;
	double ev = pow(2.0, (ui.ctl[4] - 6) * 0.5) * (cs.digital > 1 ? cs.digital : 1);
	/* 16 times 10 bits above black, to the 12 bits of the curve; 256 is one */
	double range = 4095.0 / ((cs.white - cs.black) * 16.0);
	int kg = (int)(range * ev * 256), kr = (int)(range * ev * wr * 256), kb = (int)(range * ev * wbl * 256);
	int w = p->w, h = p->h;
	camss_despeckle(p->g, w, h);
	camss_despeckle(p->r, w, h);	/* or a hot pixel is a red blot on the colour's smaller plane */
	camss_despeckle(p->b, w, h);
	/* The colour's plane: a cell for every 4x4 of a photo. A preview's pixels are each far more
	 * of the sensor, so every 2x2, or the colour lands a long way from its edge. */
	int cell = w < 1000 ? 2 : 4, cshift = cell == 2 ? 1 : 2, sample = cell / 2;
	int per_cell = (cell / sample) * (cell / sample);
	int cw = (w + cell - 1) / cell, ch = (h + cell - 1) / cell;
	int clip = (int)((cs.white - cs.black) * 16 * 0.85);
	for (int cy = 0; cy < ch; cy++) {
		int32_t *cr = p->cr + (size_t)cy * cw, *cb = p->cb + (size_t)cy * cw;
		memset(cr, 0, sizeof(int32_t) * cw);
		memset(cb, 0, sizeof(int32_t) * cw);
		for (int y = cy * cell; y < cy * cell + cell; y += sample) {
			int yy = y < h ? y : h - 1;
			const int16_t *rp = p->r + (size_t)yy * w, *gp = p->g + (size_t)yy * w, *bp = p->b + (size_t)yy * w;
			for (int x = 0; x < w; x += sample) {
				if (rp[x] >= clip || gp[x] >= clip || bp[x] >= clip) {
					continue;
				}
				int g = gp[x] * kg >> 8;
				cr[x >> cshift] += (rp[x] * kr >> 8) - g;
				cb[x >> cshift] += (bp[x] * kb >> 8) - g;
			}
		}
		for (int x = 0; x < cw; x++) {
			cr[x] /= per_cell;
			cb[x] /= per_cell;
		}
	}
	/* the darker it is, the wider */
	int wide = cs.gain * 4 / (cs.gain_base > 0 ? cs.gain_base : 256);
	camss_box(p->cr, cw, ch, p->line, 1 + wide / 2);
	camss_box(p->cb, cw, ch, p->line, 1 + wide / 2);
	/* Where each pixel falls between the plane's cells: stepping from cell to cell makes blocks.
	 * 8 bits of fraction. */
	int32_t *xat = malloc(sizeof(int32_t) * w);
	if (!xat) {
		return;
	}
	for (int x = 0; x < w; x++) {
		int at = ((x * 2 + 1 - cell) * 256) / (2 * cell);
		at = at < 0 ? 0 : at;
		xat[x] = at >= (cw - 1) * 256 ? (cw - 1) * 256 - 1 : at;
		if (cw < 2) {
			xat[x] = 0;
		}
	}
	/* where (0, 0) lands and how far a step along and down the sensor goes, in pixels */
	uint8_t *out = cairo_image_surface_get_data(surface);
	int stride = cairo_image_surface_get_stride(surface) / 4;
	int ow = cairo_image_surface_get_width(surface), oh = cairo_image_surface_get_height(surface);
	if (cs.rotate == 90 || cs.rotate == 270 ? (ow < h || oh < w) : (ow < w || oh < h)) {
		free(xat);
		return;
	}
	int ox0, oy0, step_x, step_y;	/* the picture's x, y for the sensor's first; the steps below */
	int dx_x = 0, dy_x = 0, dx_y = 0, dy_y = 0;	/* d(picture)_(sensor) */
	switch (cs.rotate) {
	case 90: ox0 = h - 1; oy0 = 0; dy_x = 1; dx_y = -1; break;
	case 180: ox0 = w - 1; oy0 = h - 1; dx_x = -1; dy_y = -1; break;
	case 270: ox0 = 0; oy0 = w - 1; dy_x = -1; dx_y = 1; break;
	default: ox0 = 0; oy0 = 0; dx_x = 1; dy_y = 1; break;
	}
	if (cs.mirror) {
		bool sideways = cs.rotate == 90 || cs.rotate == 270;
		ox0 = (sideways ? h : w) - 1 - ox0;
		dx_x = -dx_x;
		dx_y = -dx_y;
	}
	step_x = dy_x * stride + dx_x;
	step_y = dy_y * stride + dx_y;
	uint32_t *line = (uint32_t *)out + (ptrdiff_t)oy0 * stride + ox0;
	for (int iy = 0; iy < h; iy++, line += step_y) {
		const int16_t *gp = p->g + (size_t)iy * w;
		int yat = ((iy * 2 + 1 - cell) * 256) / (2 * cell);
		yat = yat < 0 ? 0 : yat;
		yat = yat >= (ch - 1) * 256 ? (ch - 1) * 256 - 1 : yat;
		if (ch < 2) {
			yat = 0;
		}
		int yf = yat & 255, ynext = ch < 2 ? 0 : cw;
		const int32_t *cr = p->cr + (size_t)(yat >> 8) * cw, *cb = p->cb + (size_t)(yat >> 8) * cw;
		uint32_t *px = line;
		for (int ix = 0; ix < w; ix++, px += step_x) {
			int g = gp[ix] * kg >> 8;
			int xi = xat[ix] >> 8, xf = xat[ix] & 255, xn = cw < 2 ? 0 : 1;
			int dr = ((cr[xi] * (256 - xf) + cr[xi + xn] * xf) >> 8) * (256 - yf) +
				((cr[xi + ynext] * (256 - xf) + cr[xi + ynext + xn] * xf) >> 8) * yf;
			int db = ((cb[xi] * (256 - xf) + cb[xi + xn] * xf) >> 8) * (256 - yf) +
				((cb[xi + ynext] * (256 - xf) + cb[xi + ynext + xn] * xf) >> 8) * yf;
			dr >>= 8;
			db >>= 8;
			/* fading out towards white, where there is no colour left to show */
			if (g > 3300) {
				int left = g > 4095 ? 0 : 4095 - g;
				dr = dr * left / 795;
				db = db * left / 795;
			}
			/* a quarter stronger: sensors see colours paler than they are */
			int r = g + dr + (dr >> 2), b = g + db + (db >> 2);
			int g2 = g - (dr >> 3) - (db >> 3);
			r = r < 0 ? 0 : r > 4095 ? 4095 : r;
			g2 = g2 < 0 ? 0 : g2 > 4095 ? 4095 : g2;
			b = b < 0 ? 0 : b > 4095 ? 4095 : b;
			*px = 0xff000000u | (uint32_t)gamma[r] << 16 | (uint32_t)gamma[g2] << 8 | gamma[b];
		}
	}
	free(xat);
	cairo_surface_mark_dirty(surface);
}

/* A frame of the preview into a surface of the upright size. */
static void camss_develop(const uint8_t *in, cairo_surface_t *surface) {
	int sx, sy, cols, rows;
	camss_cells(0, &sx, &sy, &cols, &rows);
	if (!camss_planes_size(&cs_preview, cols, rows)) {
		return;
	}
	double mean[4] = { 0, 0, 0, 0 };
	camss_gather(in, &cs_preview, sx, sy, mean);
	camss_render(&cs_preview, surface);
	if (mean[1] > 0 && !ui.ctl[0] && mean[0] > 1 && mean[2] > 1) {
		double tr = mean[1] / mean[0], tb = mean[1] / mean[2];
		tr = tr > 3 ? 3 : tr < 0.8 ? 0.8 : tr;
		tb = tb > 3 ? 3 : tb < 0.8 ? 0.8 : tb;
		cs.wb_r += (tr - cs.wb_r) * 0.08;
		cs.wb_b += (tb - cs.wb_b) * 0.08;
	}
	if (!(cs.seq % 3)) {
		camss_expose(mean[1], mean[3]);
	}
	cs.seq++;
}

/* The next frame's buffer, or -1. Requeue it with camss_requeue(). */
static int camss_dequeue(struct v4l2_buffer *b, struct v4l2_plane *plane) {
	memset(b, 0, sizeof(*b));
	memset(plane, 0, sizeof(*plane));
	b->type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	b->memory = V4L2_MEMORY_MMAP;
	b->m.planes = plane;
	b->length = 1;
	if (ioctl(cs.fd, VIDIOC_DQBUF, b) != 0 || b->index >= (unsigned)cs.nbuf) {
		return -1;
	}
	return b->flags & V4L2_BUF_FLAG_ERROR ? -2 : (int)b->index;
}

static void camss_requeue(struct v4l2_buffer *b) {
	ioctl(cs.fd, VIDIOC_QBUF, b);
}

/* The preview's work takes tens of milliseconds a frame: on a thread of its own, so that a
 * finger on the controls never waits for it. A frame that comes while it is busy just goes
 * back to the driver. */
static void *camss_worker(void *unused) {
	(void)unused;
	pthread_mutex_lock(&cs.lock);
	while (!cs.quit) {
		if (cs.held < 0) {
			pthread_cond_wait(&cs.wake, &cs.lock);
			continue;
		}
		int i = cs.held;
		pthread_mutex_unlock(&cs.lock);
		camss_develop(cs.buf[i].start, cs.back);
		uint64_t one = 1;
		if (write(cs.done_fd, &one, sizeof(one)) < 0) {
			/* the main loop goes on with the last frame */
		}
		pthread_mutex_lock(&cs.lock);
		while (!cs.quit && !cs.collected) {
			pthread_cond_wait(&cs.wake, &cs.lock);
		}
		cs.collected = false;
		cs.held = -1;
	}
	pthread_mutex_unlock(&cs.lock);
	return NULL;
}

static bool camss_worker_start(int w, int h) {
	cs.back = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h);
	cs.done_fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
	cs.quit = cs.collected = false;
	cs.held = -1;
	if (cs.done_fd < 0 || pthread_create(&cs.thread, NULL, camss_worker, NULL) != 0) {
		if (cs.done_fd >= 0) {
			close(cs.done_fd);
		}
		cs.done_fd = -1;
		cairo_surface_destroy(cs.back);
		cs.back = NULL;
		return false;
	}
	cs.worker = true;
	return true;
}

static void camss_worker_stop(void) {
	if (!cs.worker) {
		return;
	}
	pthread_mutex_lock(&cs.lock);
	cs.quit = true;
	pthread_cond_broadcast(&cs.wake);
	pthread_mutex_unlock(&cs.lock);
	pthread_join(cs.thread, NULL);
	cs.worker = false;
	close(cs.done_fd);
	cs.done_fd = -1;
	cairo_surface_destroy(cs.back);
	cs.back = NULL;
}

/* A frame for the worker, if it is free. If not, it goes straight back. */
static void camss_worker_give(struct v4l2_buffer *b, int i) {
	pthread_mutex_lock(&cs.lock);
	bool free_now = cs.held < 0;
	if (free_now) {
		cs.held = i;
		cs.held_buf = *b;
		pthread_cond_broadcast(&cs.wake);
	}
	pthread_mutex_unlock(&cs.lock);
	if (!free_now) {
		ioctl(cs.fd, VIDIOC_QBUF, b);
	}
}

/* The main loop's half: the finished picture, swapped in; its buffer back to the driver. */
static cairo_surface_t *camss_worker_collect(cairo_surface_t *frame) {
	uint64_t count;
	if (read(cs.done_fd, &count, sizeof(count)) < 0) {
		return frame;
	}
	cairo_surface_t *done = cs.back;
	cs.back = frame;
	pthread_mutex_lock(&cs.lock);
	struct v4l2_plane plane;
	memset(&plane, 0, sizeof(plane));
	struct v4l2_buffer b = cs.held_buf;
	b.m.planes = &plane;
	b.length = 1;
	ioctl(cs.fd, VIDIOC_QBUF, &b);
	cs.collected = true;
	pthread_cond_broadcast(&cs.wake);
	pthread_mutex_unlock(&cs.lock);
	return done;
}

static void camss_size(int full, int *w, int *h);

static bool camss_open(enum camss_cam cam) {
	camss_close();
	if (cam != cs.cam && cs.exposure) {
		cs.saved[cs.cam].exposure = cs.exposure;
		cs.saved[cs.cam].gain = cs.gain;
		cs.saved[cs.cam].digital = cs.digital;
		cs.saved[cs.cam].wb_r = cs.wb_r;
		cs.saved[cs.cam].wb_b = cs.wb_b;
		cs.exposure = cs.saved[cam].exposure;
		cs.gain = cs.saved[cam].gain;
		cs.digital = cs.saved[cam].exposure ? cs.saved[cam].digital : 1;
		cs.wb_r = cs.saved[cam].exposure ? cs.saved[cam].wb_r : 1.6;
		cs.wb_b = cs.saved[cam].exposure ? cs.saved[cam].wb_b : 1.6;
	}
	cs.cam = cam;
	if (!camss_route("preview")) {
		return false;
	}
	cs.line_preview = cs.line;
	if (!cs.exposure) {
		cs.exposure = 1000;
	}
	cs.seq = 0;
	if (!camss_stream_start()) {
		return false;
	}
	int w, h;
	camss_size(0, &w, &h);
	return camss_worker_start(w, h);
}

/* The upright size for this mode */
static void camss_size(int full, int *w, int *h) {
	int sx, sy, cols, rows;
	camss_cells(full, &sx, &sy, &cols, &rows);
	bool sideways = cs.rotate == 90 || cs.rotate == 270;
	*w = sideways ? rows : cols;
	*h = sideways ? cols : rows;
}

/* A photo at the sensor's full size: a route of its own, the same light as the preview
 * (a row takes longer there, so fewer of them). Blocks for some seconds. The preview is
 * running again when it returns, whatever became of the photo. */
static cairo_surface_t *camss_capture(void) {
	cairo_surface_t *shot = NULL;
	int exposure = cs.exposure;
	camss_stream_stop();
	if (camss_route("photo")) {
		if (cs.line > 0 && cs.line_preview > 0) {
			cs.exposure = (int)((double)exposure * cs.line_preview / cs.line);
			if (cs.exposure < 4) {
				cs.exposure = 4;
			}
		}
		if (camss_stream_start()) {
			/* a frame for the new exposure to take, then the ones to read, averaged */
			struct camss_planes planes;
			int sx, sy, cols, rows, used = 0;
			memset(&planes, 0, sizeof(planes));
			camss_cells(1, &sx, &sy, &cols, &rows);
			if (camss_planes_size(&planes, cols, rows)) {
				for (int got = 0; got < 1 + CAMSS_PHOTO_FRAMES; ) {
					struct pollfd p = { .fd = cs.fd, .events = POLLIN };
					if (poll(&p, 1, 4000) <= 0) {
						break;
					}
					struct v4l2_buffer b;
					struct v4l2_plane plane;
					int i = camss_dequeue(&b, &plane);
					if (i == -1) {
						continue;
					}
					got++;
					if (i >= 0 && got > 1 && cs.buf[i].len >= (size_t)cs.pitch * cs.h) {
						camss_gather(cs.buf[i].start, &planes, sx, sy, NULL);
						used++;
					}
					camss_requeue(&b);
				}
				if (used) {
					int w, h;
					camss_size(1, &w, &h);
					shot = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h);
					camss_render(&planes, shot);
				}
			}
			camss_planes_free(&planes);
		}
		camss_stream_stop();
	}
	cs.exposure = exposure;
	if (camss_route("preview")) {
		cs.line_preview = cs.line;
		if (camss_stream_start()) {
			int w, h;
			camss_size(0, &w, &h);
			camss_worker_start(w, h);
		}
	}
	return shot;
}
