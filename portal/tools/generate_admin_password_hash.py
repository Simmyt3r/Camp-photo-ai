from getpass import getpass
from werkzeug.security import generate_password_hash

password = getpass("Admin password: ")
confirm = getpass("Confirm password: ")
if not password or password != confirm:
    raise SystemExit("Passwords do not match or are empty.")
print(generate_password_hash(password))
