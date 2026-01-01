def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}!"


def main() -> None:
    """Main entry point."""
    message = greet("World")
    print(message)


if __name__ == "__main__":
    main()
