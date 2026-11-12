"""Small command-line helper.

    python manage.py init                    create tables / rooms / accounts
    python manage.py set-password <username>  change an account password
"""
import getpass
import sys

import auth
import database as db


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "init":
        db.init_db()
        print(f"Database ready ({db.backend_name()}).")
        return 0
    if len(argv) == 3 and argv[1] == "set-password":
        db.init_db()
        pw = getpass.getpass("New password: ")
        if pw != getpass.getpass("Repeat password: "):
            print("Passwords do not match.")
            return 1
        print("Password updated." if auth.set_password(argv[2], pw) else "No such user.")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
