#!/bin/bash
# Vs-01 one-time setup. Runs as root at boot via systemd.run= in cmdline.txt, then removes that hook and reboots.
# show everything on the HDMI console (there is no network to debug over), and keep a copy in the boot partition
exec >/dev/tty1 2>&1
echo; echo "=== Vs-01 setup $(date) ==="
BOOT=/boot/firmware
mount | grep -E ' / | /boot' 
mount -o remount,rw / ; mount -o remount,rw $BOOT 2>/dev/null || mount $BOOT
exec > >(tee -a $BOOT/vs01/setup_log.txt) 2>&1
trap 'echo "!!! command failed at line $LINENO (continuing)"' ERR
set -x
# a login user if this image never ran its first-boot wizard (console only; there is no network)
if ! getent passwd 1000 >/dev/null; then useradd -m -G video,render,input,dialout,sudo -s /bin/bash vs; echo 'vs:vs01' | chpasswd; fi
systemctl disable userconfig.service 2>/dev/null || true; rm -f /etc/xdg/autostart/piwiz.desktop
# no desktop: the player owns the HDMI output through KMS
systemctl set-default multi-user.target
systemctl disable lightdm.service 2>/dev/null || true
# the UART is for the control boards, not a login console
systemctl disable serial-getty@ttyAMA0.service serial-getty@serial0.service 2>/dev/null || true
cat >/etc/systemd/system/vs01-player.service <<EOF
[Unit]
Description=Vs-01 GLSL player
After=systemd-user-sessions.service plymouth-quit-wait.service
[Service]
ExecStart=/usr/bin/python3 $BOOT/vs01/player.py $BOOT/vs01
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
EOF
systemctl enable vs01-player.service
sed -i 's| systemd.run=[^ ]*||; s| systemd.run_success_action=[^ ]*||; s| systemd.unit=kernel-command-line.target||' $BOOT/cmdline.txt
sync
echo "=== done, rebooting in 5 s"; sleep 5
exit 0
