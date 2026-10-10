from pipeline.cli import build_parser


def test_cli_parser_accepts_thread_id():
    parser = build_parser()
    args = parser.parse_args(["--thread-id", "thread-123"])
    assert args.thread_id == "thread-123"

