// SPDX-License-Identifier: GPL-2.0-only
// Preloaded into graphical sessions: SM8550 firmware disables SVE, but LLVM derives SVE from the
// core names in /proc/cpuinfo (Cortex-A510/A715/X3), so llvmpipe's JIT emits SVE and dies with
// SIGILL. Report an SVE-less core instead; features still come from /proc/cpuinfo.
struct string_ref { const char *data; unsigned long length; };

struct string_ref _ZN4llvm3sys14getHostCPUNameEv(void)
{
	return (struct string_ref){ "cortex-a78", 10 };
}
