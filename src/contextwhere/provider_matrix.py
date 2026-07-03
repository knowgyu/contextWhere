from __future__ import annotations


def provider_matrix() -> dict:
    providers = [
        {
            "provider": "mailwhere",
            "status": "supported",
            "transport": "local CLI",
            "live_requirement": "MailWhere.Cli.exe available on PATH or supplied with --mailwhere-command",
            "optional_config": ["--mailwhere-db"],
            "ingest_kinds": ["task", "review_candidate"],
            "read_only": True,
            "mutating_actions": [],
            "safety_boundaries": [
                "raw mail body omitted by default",
                "full addresses and attachments omitted by default",
                "no open/reply/move/delete actions",
            ],
            "fixture_supported": True,
        },
        {
            "provider": "officewhere",
            "status": "supported",
            "transport": "loopback HTTP",
            "live_requirement": "--officewhere-base-url must be localhost, 127.0.0.1, or ::1",
            "optional_config": [],
            "ingest_kinds": ["document"],
            "read_only": True,
            "mutating_actions": [],
            "safety_boundaries": [
                "non-loopback URLs rejected",
                "local paths omitted by default",
                "no open/reindex/rescan actions",
            ],
            "fixture_supported": True,
        },
    ]
    return {
        "ok": True,
        "format": "contextwhere-provider-matrix-v1",
        "providers": providers,
        "provider_count": len(providers),
    }
