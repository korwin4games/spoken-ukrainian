"""Numeric namesake fingerprint; independent implementation of pinned string_hash.

This is not a canonical Spoken ID and does not prove a page-chain join.
Normalization/case conversion must be reviewed separately for each input language.
"""

def string_hash(text):
    data = text.encode('utf-8')
    if not data:
        return 0
    counter = 1
    size = len(data)
    for i in range(0, size, 3):
        pad = size - i + 255
        counter = ((counter * 8161) % 4294967279 + data[i] * 16776193
                   + (data[i + 1] if i + 1 < size else pad) * 8372226
                   + (data[i + 2] if i + 2 < size else pad) * 3932164)
    return counter % 4294967291
