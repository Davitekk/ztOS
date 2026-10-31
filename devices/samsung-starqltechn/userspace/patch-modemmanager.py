#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ModemManager 1.24.2: a use-after-free in its netlink transactions.

transaction_complete() removes the transaction from self->transactions, whose
destroy function frees it (transaction_free), and then calls
tr->completion_fn: freed memory. On this phone every mobile data connection
creates and deletes the modem's rmnet link over netlink, and turning data off
and on made ModemManager jump to a garbage address (SIGSEGV in
transaction_complete, mm-netlink.c:242, with a debug build) about one
reconnection in two; the SIM was gone until it had restarted. With the
function taken first, six off/on cycles in a row, no crash.

Asserted, so a changed upstream file fails instead of silently building
without it. Takes ModemManager's source directory as its only argument.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "src/mm-netlink.c"
src = path.read_text()
old = ("    GTask *task;\n"
       "    guint32 sequence_id;\n"
       "\n"
       "    task = g_steal_pointer (&tr->completion_task);\n"
       "    sequence_id = tr->sequence_id;\n"
       "\n"
       "    g_hash_table_remove (tr->self->transactions,\n"
       "                         GUINT_TO_POINTER (tr->sequence_id));\n"
       "\n"
       "    if (!saved_errno) {\n"
       "        GError *error = NULL;\n"
       "\n"
       "        if (!tr->completion_fn (task, hdr, &error))\n")
new = ("    GTask *task;\n"
       "    guint32 sequence_id;\n"
       "    MsgFunc completion_fn;\n"
       "\n"
       "    task = g_steal_pointer (&tr->completion_task);\n"
       "    sequence_id = tr->sequence_id;\n"
       "    /* ztOS: removing it frees it (transaction_free): what is needed of it first */\n"
       "    completion_fn = tr->completion_fn;\n"
       "\n"
       "    g_hash_table_remove (tr->self->transactions,\n"
       "                         GUINT_TO_POINTER (tr->sequence_id));\n"
       "\n"
       "    if (!saved_errno) {\n"
       "        GError *error = NULL;\n"
       "\n"
       "        if (!completion_fn (task, hdr, &error))\n")
if new not in src:
    assert src.count(old) == 1, "mm-netlink.c changed: look at transaction_complete again"
    path.write_text(src.replace(old, new))
    print("mm-netlink.c: transaction_complete without the use-after-free")
else:
    print("mm-netlink.c: already patched")
