import bcrypt


def get_hashed_password(plain_text_password):
    """Hashes a plain text password using bcrypt.

    This function takes a plain text password as input and returns its hashed version using the bcrypt hashing algorithm. The hashing process includes generating a salt to ensure that the same password will produce different hashes each time it is hashed.

    Args:
        plain_text_password (str): The plain text password to be hashed.

    Returns:
        str: The hashed version of the input password.
    """
    return bcrypt.hashpw(plain_text_password, bcrypt.gensalt())


def check_password(plain_text_password, hashed_password):
    """Checks a plain text password against a hashed password using bcrypt.

    This function takes a plain text password and a hashed password as input and
    verifies whether the plain text password, when hashed, matches the
    provided hashed password. This is done using the bcrypt library,
    which handles the salt and hashing process internally.

    Args:
        plain_text_password (str): The plain text password to be checked.
        hashed_password (str): The hashed password to check against.

    Returns:
        bool: True if the passwords match, False otherwise.
    """
    return bcrypt.checkpw(plain_text_password, hashed_password)
