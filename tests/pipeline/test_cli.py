from pipeline.cli import build_parser


def test_cli_parser_accepts_no_special_arguments():
    parser = build_parser()
    args = parser.parse_args([])
    assert vars(args) == {}
