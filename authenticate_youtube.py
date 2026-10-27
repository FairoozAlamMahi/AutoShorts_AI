"""One-Click YouTube Brand Account Authenticator for ShortsFactory."""
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.youtube_uploader import YouTubeUploader


def main():
    print("=" * 65)
    print("  ShortsFactory Local — YouTube Channel OAuth2 Authenticator")
    print("=" * 65)

    data_dir = PROJECT_ROOT / "data"
    client_secrets = data_dir / "client_secrets.json"
    token_file = data_dir / "youtube_token.json"

    if not client_secrets.exists():
        print(f"\n[ERROR] client_secrets.json not found at:\n  {client_secrets}")
        print("\nPlease follow these 3 steps first:")
        print("1. Go to Google Cloud Console (https://console.cloud.google.com/)")
        print("2. Create an OAuth 2.0 Client ID (Application Type: Desktop App)")
        print(f"3. Download the JSON file and save it as: {client_secrets}\n")
        sys.exit(1)

    print(f"\n[INFO] Found client_secrets.json at {client_secrets}")
    print("[INFO] Launching browser to authorize your YouTube Brand Account...")
    print("[INFO] A Google sign-in window will open in your default browser.\n")

    uploader = YouTubeUploader(
        client_secrets_path=client_secrets,
        token_path=token_file,
    )

    success, message = uploader.authenticate_interactive()
    if success:
        print("\n" + "=" * 65)
        print(f"  SUCCESS: {message}")
        print(f"  Token securely saved to: {token_file}")
        print("  AutoShorts AI can now publish shorts and sync telemetry!")
        print("=" * 65 + "\n")
    else:
        print(f"\n[FAILED] {message}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
