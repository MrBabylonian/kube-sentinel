from structlog import get_logger


def main() -> None:
    """Main entry point for the kube-sentinel application."""
    logger = get_logger()
    logger.info("Starting kube-sentinel...")
    # TODO: Add main application logic here


if __name__ == "__main__":
    main()
