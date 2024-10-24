import sys
sys.path.append("src")

from EncryptionSystem import encryption_logic


class EncryptDecryptWithoutKey(Exception):
    """
    Custom exception to indicate that the entered key is empty
    """

    def __init__(self):
        super().__init__(f"Cannot encrypt or decrypt if the key is empty, please try entering a valid key.")

class EncryptDecryptEmptyMessage(Exception):
    """
    Custom exception to indicate that the entered message is empty
    """

    def __init__(self):
        super().__init__(f"Cannot encrypt or an empty message, please try entering a valid message.")

class InvalidKeyLength(Exception):
    """
    Custom exception to indicate that the length of the entered key is invalid
    """

    def __init__(self):
        super().__init__(f"Invalid key length, please try entering a valid key. The key must have exactly 16, 24 or 32 characters")


class UnsupportedMessageType(Exception):
    """
    Custom exception to indicate that the entered message is not valid
    """

    def __init__(self):
        super().__init__(f"Unsupported message type, please try entering a valid message.")


class IncorrectKey(Exception):
    """
    Custom exception to indicate that the entered key is incorrect
    """
    def __init__(self):
        super().__init__(f"Key is incorrect, please try entering a valid key.")


class AES:
    """
    Class for AES-128 encryption with CBC mode and PKCS#7.
    This is a raw implementation of AES, without key stretching or IV
    management. Unless you need that, please use `encrypt` and `decrypt`.
    """
    rounds_by_key_size = {16: 10, 24: 12, 32: 14}
    def __init__(self, master_key):
        """
        Initializes the object with a given key.
        """
        assert len(master_key) in AES.rounds_by_key_size
        self.n_rounds = AES.rounds_by_key_size[len(master_key)]
        self._key_matrices = self._expand_key(master_key)


    def _expand_key(self, master_key):
        """
        Expands and returns a list of key matrices for the given master_key.
        """
        # Initialize round keys with raw key material.
        key_columns = encryption_logic.bytes2matrix(master_key)
        iteration_size = len(master_key) // 4

        i = 1
        while len(key_columns) < (self.n_rounds + 1) * 4:
            # Copy previous word.
            word = list(key_columns[-1])

            # Perform schedule_core once every "row".
            if len(key_columns) % iteration_size == 0:
                # Circular shift.
                word.append(word.pop(0))
                # Map to S-BOX.
                word = [encryption_logic.s_box[b] for b in word]
                # XOR with first byte of R-CON, since the others bytes of R-CON are 0.
                word[0] ^= encryption_logic.r_con[i]
                i += 1
            elif len(master_key) == 32 and len(key_columns) % iteration_size == 4:
                # Run word through S-box in the fourth iteration when using a
                # 256-bit key.
                word = [encryption_logic.s_box[b] for b in word]

            # XOR with equivalent word from previous iteration.
            word = encryption_logic.xor_bytes(word, key_columns[-iteration_size])
            key_columns.append(word)

        # Group key words in 4x4 byte matrices.
        return [key_columns[4*i : 4*(i+1)] for i in range(len(key_columns) // 4)]

    def encrypt_block(self, plaintext):
        """
        Encrypts a single block of 16 byte long plaintext.
        """
        assert len(plaintext) == 16

        plain_state = encryption_logic.bytes2matrix(plaintext)

        encryption_logic.add_round_key(plain_state, self._key_matrices[0])

        for i in range(1, self.n_rounds):
            encryption_logic.sub_bytes(plain_state)
            encryption_logic.shift_rows(plain_state)
            encryption_logic.mix_columns(plain_state)
            encryption_logic.add_round_key(plain_state, self._key_matrices[i])

        encryption_logic.sub_bytes(plain_state)
        encryption_logic.shift_rows(plain_state)
        encryption_logic.add_round_key(plain_state, self._key_matrices[-1])

        return encryption_logic.matrix2bytes(plain_state)

    def decrypt_block(self, ciphertext):
        """
        Decrypts a single block of 16 byte long ciphertext.
        """
        assert len(ciphertext) == 16

        cipher_state = encryption_logic.bytes2matrix(ciphertext)

        encryption_logic.add_round_key(cipher_state, self._key_matrices[-1])
        encryption_logic.inv_shift_rows(cipher_state)
        encryption_logic.inv_sub_bytes(cipher_state)

        for i in range(self.n_rounds - 1, 0, -1):
            encryption_logic.add_round_key(cipher_state, self._key_matrices[i])
            encryption_logic.inv_mix_columns(cipher_state)
            encryption_logic.inv_shift_rows(cipher_state)
            encryption_logic.inv_sub_bytes(cipher_state)

        encryption_logic.add_round_key(cipher_state, self._key_matrices[0])

        return encryption_logic.matrix2bytes(cipher_state)

    def encrypt_cbc(self, plaintext, iv):
        """
        Encrypts `plaintext` using CBC mode and PKCS#7 padding, with the given
        initialization vector (iv).
        """
        assert len(iv) == 16

        plaintext = encryption_logic.pad(plaintext)

        blocks = []
        previous = iv
        for plaintext_block in encryption_logic.split_blocks(plaintext):
            # CBC mode encrypt: encrypt(plaintext_block XOR previous)
            block = self.encrypt_block(encryption_logic.xor_bytes(plaintext_block, previous))
            blocks.append(block)
            previous = block

        return b''.join(blocks)

    def decrypt_cbc(self, ciphertext, iv):
        """
        Decrypts `ciphertext` using CBC mode and PKCS#7 padding, with the given
        initialization vector (iv).
        """
        assert len(iv) == 16

        blocks = []
        previous = iv
        for ciphertext_block in encryption_logic.split_blocks(ciphertext):
            # CBC mode decrypt: previous XOR decrypt(ciphertext)
            blocks.append(encryption_logic.xor_bytes(previous, self.decrypt_block(ciphertext_block)))
            previous = ciphertext_block

        return encryption_logic.unpad(b''.join(blocks))



import os
from hashlib import pbkdf2_hmac
from hmac import new as new_hmac, compare_digest

AES_KEY_SIZE = 16
HMAC_KEY_SIZE = 16
IV_SIZE = 16

SALT_SIZE = 16
HMAC_SIZE = 32

def get_key_iv(password, salt, workload=100000):
    """
    Stretches the password and extracts an AES key, an HMAC key and an AES
    initialization vector.
    """
    stretched = pbkdf2_hmac('sha256', password, salt, workload, AES_KEY_SIZE + IV_SIZE + HMAC_KEY_SIZE)
    aes_key, stretched = stretched[:AES_KEY_SIZE], stretched[AES_KEY_SIZE:]
    hmac_key, stretched = stretched[:HMAC_KEY_SIZE], stretched[HMAC_KEY_SIZE:]
    iv = stretched[:IV_SIZE]
    return aes_key, hmac_key, iv

def validate_encryption_inputs(key, plaintext):
    if key is None or len(key) == 0:
        raise EncryptDecryptWithoutKey()
    if not plaintext:
        raise EncryptDecryptEmptyMessage()
    if len(key) not in [16, 24, 32]:
        raise InvalidKeyLength()
    for char in plaintext.decode('utf-8'):
        if ord(char) > 127:  # Si el valor Unicode es mayor que 127, no es ASCII
            raise UnsupportedMessageType()

def encrypt(key, plaintext, workload=100000):
    """
    Encrypts `plaintext` with `key` using AES-128, an HMAC to verify integrity,
    and PBKDF2 to stretch the given key.

    The exact algorithm is specified in the module docstring.
    """

    if isinstance(key, str):
        key = key.encode('utf-8')
    if isinstance(plaintext, str):
        plaintext = plaintext.encode('utf-8')

    validate_encryption_inputs(key, plaintext)

    salt = os.urandom(SALT_SIZE)
    key, hmac_key, iv = get_key_iv(key, salt, workload)
    ciphertext = AES(key).encrypt_cbc(plaintext, iv)
    hmac = new_hmac(hmac_key, salt + ciphertext, 'sha256').digest()
    assert len(hmac) == HMAC_SIZE

    return hmac + salt + ciphertext


def validate_decryption_inputs(key, ciphertext):
    if key is None or len(key) == 0:
        raise EncryptDecryptWithoutKey()
    if not ciphertext:
        raise EncryptDecryptEmptyMessage()
    if len(key) not in [16, 24, 32]:
        raise InvalidKeyLength()

def decrypt(key, ciphertext, workload=100000):
    """
    Decrypts `ciphertext` with `key` using AES-128, an HMAC to verify integrity,
    and PBKDF2 to stretch the given key.

    The exact algorithm is specified in the module docstring.
    """

    validate_decryption_inputs(key, ciphertext)


    assert len(ciphertext) % 16 == 0, "Ciphertext must be made of full 16-byte blocks."

    assert len(ciphertext) >= 32, """
    Ciphertext must be at least 32 bytes long (16 byte salt + 16 byte block). To
    encrypt or decrypt single blocks use `AES(key).decrypt_block(ciphertext)`.
    """

    if isinstance(key, str):
        key = key.encode('utf-8')

    hmac, ciphertext = ciphertext[:HMAC_SIZE], ciphertext[HMAC_SIZE:]
    salt, ciphertext = ciphertext[:SALT_SIZE], ciphertext[SALT_SIZE:]
    key, hmac_key, iv = get_key_iv(key, salt, workload)

    expected_hmac = new_hmac(hmac_key, salt + ciphertext, 'sha256').digest()
    assert compare_digest(hmac, expected_hmac), 'Ciphertext corrupted or tampered.'

    return AES(key).decrypt_cbc(ciphertext, iv)
