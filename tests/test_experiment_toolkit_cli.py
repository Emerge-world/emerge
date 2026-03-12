from experiment_toolkit import build_parser


def test_cli_accepts_suite_config_and_output_dir():
    parser = build_parser()
    args = parser.parse_args(["suite.yaml", "--output-dir", "artifacts"])

    assert args.config == "suite.yaml"
    assert args.output_dir == "artifacts"
