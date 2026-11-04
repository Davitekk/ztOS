#!/usr/bin/env python3
"""The Lumia 950's frames: tell DRM a commit is on the hardware when it is.

msm signals hw_done only after wait_flush. On a command-mode panel that wait ends when
the transfer does (pp done), about 15 ms after the page flip event, and two things hang
on it:

- The unused cursor plane wlroots puts in every commit is tracked by a "fake commit",
  whose flip_done comes with hw_done. The compositor's next commit, sent on the flip
  event, found the plane "busy with a previous commit" and failed with -EBUSY: 60 frames
  a second drawn, 16 reaching the panel.
- Past that, drm_atomic_helper_swap_state() stalls the next commit's ioctl on hw_done, so
  the compositor sat 13.5 ms of each 16.7 ms frame in a "nonblocking" commit, and the
  next frame went from pp done to the panel through three threads in turn, with about
  1.3 ms to spare before the next transfer has to start.

Signal hw_done once the commit has been flushed, as the DRM helpers' own commit_tail
does and as this function's async path already does. The next commit's tail still begins
by waiting for the flush (under the CRTC lock), so it does not touch the hardware early;
it is simply already waiting when pp done comes. mdp5_complete_commit may now run on
SMP state a newer commit has swapped in, which only clears FIFO thresholds of pipes that
commit no longer uses, after the transfer has ended.

Usage: patch-msm-hw-done.py <kernel source>
"""
import sys
from pathlib import Path

ATOMIC = "drivers/gpu/drm/msm/msm_atomic.c"
FLUSHED = """	kms->funcs->flush_commit(kms, crtc_mask);
	unlock_crtcs(kms, crtc_mask);
"""
WAS = """	kms->funcs->disable_commit(kms);

	drm_atomic_helper_commit_hw_done(state);
	drm_atomic_helper_cleanup_planes(dev, state);
"""
NOW = """	kms->funcs->disable_commit(kms);

	drm_atomic_helper_cleanup_planes(dev, state);
"""
ADDED = """
	/* On the hardware: the next commit may be set up while this one transfers */
	drm_atomic_helper_commit_hw_done(state);

"""


def main() -> None:
    path = Path(sys.argv[1]) / ATOMIC
    text = path.read_text()
    for anchor in (FLUSHED, WAS):
        if text.count(anchor) != 1:
            sys.exit(f"patch-msm-hw-done: {ATOMIC}: anchor not found once: {anchor!r}")
    text = text.replace(FLUSHED, FLUSHED + ADDED).replace(WAS, NOW)
    path.write_text(text)
    print("patch-msm-hw-done: hw_done when the commit is flushed, not when it has transferred")


if __name__ == "__main__":
    main()
