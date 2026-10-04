"""Solver del desafio de produccion (Anexo 4 del enunciado).

Regla: leadingZeroBits(sha256(prefix + ":" + nonce)) >= difficulty
"""
import hashlib
import time


def leading_zero_bits(digest: bytes) -> int:
    # Equivalente a contar bits cero del hash en hexadecimal, pero mas rapido
    return 256 - int.from_bytes(digest, "big").bit_length()


def solve(prefix: str, difficulty: int, max_seconds: float = 240) -> str | None:
    """Devuelve el nonce como string, o None si no alcanza antes de max_seconds
    (el challenge expira a los 5 minutos)."""
    base = hashlib.sha256(f"{prefix}:".encode())  # se reutiliza el prefijo ya hasheado
    deadline = time.monotonic() + max_seconds
    nonce = 0
    while True:
        h = base.copy()
        h.update(str(nonce).encode())
        if leading_zero_bits(h.digest()) >= difficulty:
            return str(nonce)
        nonce += 1
        if nonce % 100_000 == 0 and time.monotonic() > deadline:
            return None


# --- Verificacion contra el solver de referencia del enunciado ---
def _reference_leading_zero_bits(hex_hash: str) -> int:
    bits = 0
    for ch in hex_hash:
        n = int(ch, 16)
        if n == 0:
            bits += 4
            continue
        if n < 2: bits += 3
        elif n < 4: bits += 2
        elif n < 8: bits += 1
        break
    return bits


if __name__ == "__main__":
    for difficulty in (8, 12, 16, 20):
        t0 = time.time()
        nonce = solve("test-prefix", difficulty)
        hex_hash = hashlib.sha256(f"test-prefix:{nonce}".encode()).hexdigest()
        assert _reference_leading_zero_bits(hex_hash) >= difficulty
        print(f"difficulty={difficulty:2d} nonce={nonce:>8} {time.time() - t0:.2f}s OK")
