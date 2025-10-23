"""
RSA Key Pair Generator for JWT Authentication
Generates private and public keys for RS256 algorithm
"""
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import os


def generate_rsa_keys():
    """
    Generate RSA key pair for JWT signing

    Creates:
    - private_key.pem: For signing JWT tokens (keep secret!)
    - public_key.pem: For verifying JWT tokens (can be shared)
    """

    print("🔐 Generating RSA Key Pair...")
    print("-" * 50)

    # Generate private key (4096 bits for production security)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend()
    )

    # Get public key from private key
    public_key = private_key.public_key()

    # Serialize private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key to PEM format
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Write private key to file
    private_key_path = "private_key.pem"
    with open(private_key_path, "wb") as f:
        f.write(private_pem)
    print(f"✅ Private key saved to: {private_key_path}")

    # Write public key to file
    public_key_path = "public_key.pem"
    with open(public_key_path, "wb") as f:
        f.write(public_pem)
    print(f"✅ Public key saved to: {public_key_path}")

    print("-" * 50)
    print("✅ Key generation complete!")
    print()
    print("📋 Next Steps:")
    print("1. Add these keys to your .env file:")
    print()
    print("   JWT_PRIVATE_KEY=")
    print('   """')
    print(private_pem.decode('utf-8'))
    print('   """')
    print()
    print("   JWT_PUBLIC_KEY=")
    print('   """')
    print(public_pem.decode('utf-8'))
    print('   """')
    print()
    print("⚠️  IMPORTANT:")
    print("   - Keep private_key.pem SECRET (add to .gitignore)")
    print("   - Never commit private_key.pem to version control")
    print("   - Public key can be shared safely")
    print()
    print("🔒 Security Tips:")
    print("   - Rotate keys periodically (every 6-12 months)")
    print("   - Use different keys for dev/staging/production")
    print("   - Store production keys in secure vault (e.g., AWS Secrets Manager)")

    # Set restrictive permissions on private key (Unix/Linux only)
    try:
        os.chmod(private_key_path, 0o600)
        print(f"   - Set permissions on {private_key_path} to 600 (owner read/write only)")
    except:
        pass


def verify_keys():
    """Verify that generated keys can be loaded"""
    print()
    print("🔍 Verifying generated keys...")

    try:
        # Load private key
        with open("private_key.pem", "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend()
            )
        print("✅ Private key is valid")

        # Load public key
        with open("public_key.pem", "rb") as f:
            public_key = serialization.load_pem_public_key(
                f.read(),
                backend=default_backend()
            )
        print("✅ Public key is valid")

        # Verify key sizes
        private_size = private_key.key_size
        public_size = public_key.key_size
        print(f"✅ Key size: {private_size} bits")

        if private_size == public_size == 4096:
            print("✅ All checks passed! Keys are ready to use.")
        else:
            print("⚠️  Warning: Key size is not 4096 bits")

    except Exception as e:
        print(f"❌ Verification failed: {e}")


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  JWT RSA Key Generator")
    print("  For News Summarizer API")
    print("=" * 50)
    print()

    # Check if keys already exist
    if os.path.exists("private_key.pem") or os.path.exists("public_key.pem"):
        print("⚠️  Warning: Key files already exist!")
        response = input("Do you want to overwrite them? (yes/no): ").lower()
        if response not in ["yes", "y"]:
            print("❌ Aborted. Existing keys preserved.")
            exit(0)
        print()

    # Generate keys
    generate_rsa_keys()

    # Verify keys
    verify_keys()

    print()
    print("=" * 50)
    print("  Generation Complete!")
    print("=" * 50)

