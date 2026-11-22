// SPDX-License-Identifier: GPL-2.0-only
// Minimal static AArch64 program: reboot(2) with LINUX_REBOOT_CMD_RESTART2 "bootloader".
// BusyBox `reboot` cannot pass a restart command. Exits 1 if the syscall returns.
	.global _start
	.text
_start:
	movz	x0, #0xdead
	movk	x0, #0xfee1, lsl #16		// LINUX_REBOOT_MAGIC1
	movz	x1, #0x1969
	movk	x1, #0x2812, lsl #16		// LINUX_REBOOT_MAGIC2
	movz	x2, #0xc3d4
	movk	x2, #0xa1b2, lsl #16		// LINUX_REBOOT_CMD_RESTART2
	adr	x3, cmd
	mov	x8, #142			// __NR_reboot
	svc	#0
	mov	x0, #1
	mov	x8, #93				// __NR_exit
	svc	#0
cmd:
	.asciz	"bootloader"
