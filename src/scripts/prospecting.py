"""CLI local de prospecção. Não acessa e-mail, LinkedIn ou portais."""
import argparse
import json
from pathlib import Path

from src.prospecting import (
    load_events, metrics, preflight, record_event, screen_job,
)


def read_json(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objeto JSON esperado: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Triagem e rastreamento local, com fontes de evidência e prevenção de duplicatas."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    screen = sub.add_parser("screen", help="Avaliar uma vaga com evidências")
    screen.add_argument("--job", required=True)
    screen.add_argument("--profile", required=True)
    screen.add_argument("--policy", required=True)
    screen.add_argument("--tracker", default="privado/tracker.jsonl")

    check = sub.add_parser("preflight", help="Verificar bloqueios antes de um envio")
    check.add_argument("--job", required=True)
    check.add_argument("--tracker", default="privado/tracker.jsonl")
    check.add_argument("--channel", required=True, choices=["outlook", "gmail"])
    check.add_argument("--source-verified", action="store_true")
    check.add_argument("--recipient-verified", action="store_true")
    check.add_argument("--recipient", required=True)
    check.add_argument("--history-checked", action="store_true")
    check.add_argument("--demand-verified", action="store_true")
    check.add_argument("--attachment", default="")
    check.add_argument("--screen-decision", default="")

    record = sub.add_parser("record", help="Registrar status e comprovante real")
    record.add_argument("--job", required=True)
    record.add_argument("--tracker", default="privado/tracker.jsonl")
    record.add_argument("--status", required=True)
    record.add_argument("--receipt", default="")
    record.add_argument("--attachment", default="")
    record.add_argument("--source", default="")
    record.add_argument("--recipient", default="")

    report = sub.add_parser("report", help="Indicadores por candidatura única")
    report.add_argument("--tracker", default="privado/tracker.jsonl")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "screen":
            result = screen_job(
                read_json(args.job), read_json(args.profile), read_json(args.policy),
                load_events(args.tracker),
            )
        elif args.command == "preflight":
            result = preflight(
                read_json(args.job), load_events(args.tracker), channel=args.channel,
                source_verified=args.source_verified,
                recipient_verified=args.recipient_verified,
                history_checked=args.history_checked,
                demand_verified=args.demand_verified,
                attachment=args.attachment, screen_decision=args.screen_decision,
                recipient=args.recipient,
            )
        elif args.command == "record":
            result = record_event(
                args.tracker, read_json(args.job), args.status,
                receipt=args.receipt, attachment=args.attachment,
                source=args.source, recipient=args.recipient,
            )
        else:
            result = metrics(load_events(args.tracker))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "preflight" and not result["ready"]:
            return 2
        if args.command == "screen" and result["decision"] != "eligible":
            return 2
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
