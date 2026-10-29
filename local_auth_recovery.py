"""Run locally as root: reset lost local factors and invalidate sessions/PATs."""
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username')
    parser.add_argument('--confirm-user', required=True)
    parser.add_argument('--reason', required=True, choices=('lost-device', 'compromise', 'restore'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run from the Roxy-WI host console as root')
    if args.confirm_user != args.username:
        parser.error('--confirm-user must exactly match the selected account')
    os.environ['ROXYWI_PROCESS_ROLE'] = 'migrate'
    from app.modules.authentication.security import console_reset
    epoch = console_reset(args.username, args.reason)
    print(f'Local factors reset for {args.username}; security generation {epoch}. Sign in with the local password to enroll again.')


if __name__ == '__main__':
    main()
