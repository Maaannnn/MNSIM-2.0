# Remote Hosts

This file is used to manage SSH targets locally.

## Host: mat721
- Host/IP: 10.112.28.31
- User: wjw
- SSH command: ssh wjw@10.112.28.31
- Notes: Use interactive password input or SSH key authentication.

## Quick Usage
- Connect:
  ssh wjw@10.112.28.31
- Test connectivity:
  ping -c 4 10.112.28.31

## Add New Host Template
- Host: <name>
- Host/IP: <ip>
- User: <user>
- SSH command: ssh <user>@<ip>
- Notes: <notes>
