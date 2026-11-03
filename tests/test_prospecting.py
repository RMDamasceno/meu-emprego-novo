"""Testes sem serviços externos para validar bloqueios e deduplicação."""
import json
import tempfile
import unittest
from pathlib import Path

from src.prospecting import (
    canonical_url, duplicate_of, load_events, metrics, opportunity_key,
    preflight, record_event, screen_job,
)


JOB = {
    "kind": "job",
    "company": "Exemplo Tecnologia",
    "title": "SRE Sênior",
    "job_id": "SRE-2026-17",
    "url": "https://careers.example.org/jobs/17?utm_source=linkedin",
    "area": "SRE / Observabilidade",
    "seniority": "Sênior",
    "mode": "remote_br",
    "contract": "CLT",
    "mandatory_skills": ["AWS", "Terraform"],
    "desired_skills": ["Grafana"],
    "salary_monthly_brl": 15000,
    "published_at": "2026-11-02",
    "source_verified": True,
}
PROFILE = {"verified_skills": ["AWS", "Terraform", "Grafana"], "english_fluent": False}
POLICY = {
    "areas": ["SRE / Observabilidade"],
    "seniority": ["Sênior", "Especialista"],
    "modes": ["remote_br", "hybrid_sp"],
    "contracts": ["CLT", "PJ"],
    "minimum_monthly_brl": {"CLT": 12000, "PJ": 18000},
}


class ProspectingTests(unittest.TestCase):
    def test_canonical_url_preserves_functional_parameters(self):
        self.assertEqual(
            canonical_url("https://www.example.com/jobs/17?utm_source=a&id=5#apply"),
            "https://example.com/jobs/17?id=5"
        )

    def test_job_eligible_only_with_grounded_requirements(self):
        result = screen_job(JOB, PROFILE, POLICY)
        self.assertEqual(result["decision"], "eligible")
        self.assertEqual(result["score"], 100)
        self.assertFalse(result["unproven_mandatory"])

    def test_mandatory_gap_blocks_instead_of_inventing(self):
        result = screen_job(
            {**JOB, "mandatory_skills": ["AWS", "GCP"]}, PROFILE, POLICY
        )
        self.assertEqual(result["decision"], "blocked")
        self.assertEqual(result["unproven_mandatory"], ["GCP"])

    def test_unverified_language_blocks(self):
        result = screen_job({**JOB, "english_level": "fluent"}, PROFILE, POLICY)
        self.assertEqual(result["decision"], "blocked")

    def test_salary_policy_distinguishes_clt_from_pj(self):
        pj = screen_job(
            {**JOB, "contract": "PJ", "salary_monthly_brl": 15000}, PROFILE, POLICY
        )
        self.assertEqual(pj["decision"], "blocked")
        self.assertTrue(any("piso PJ" in s for s in pj["blockers"]))

    def test_unpublished_salary_needs_review(self):
        result = screen_job({**JOB, "salary_monthly_brl": None}, PROFILE, POLICY)
        self.assertEqual(result["decision"], "review")

    def test_hybrid_outside_sp_rejected(self):
        result = screen_job({**JOB, "mode": "hybrid_sp", "city": "Campinas"}, PROFILE, POLICY)
        self.assertEqual(result["decision"], "blocked")

    def test_preflight_fails_for_missing_cv_and_missing_proofs(self):
        result = preflight(
            JOB, [], channel="outlook", source_verified=True,
            recipient_verified=True, history_checked=True,
            screen_decision="eligible",
        )
        self.assertFalse(result["ready"])
        self.assertIn("Currículo anexável não encontrado.", result["blockers"])

    def test_preflight_allows_verified_application_with_cv(self):
        with tempfile.TemporaryDirectory() as folder:
            cv = Path(folder, "cv.pdf")
            cv.write_bytes(b"mock pdf bytes")
            result = preflight(
                JOB, [], channel="outlook", source_verified=True,
                recipient_verified=True, history_checked=True,
                screen_decision="eligible", attachment=str(cv),
            )
            self.assertTrue(result["ready"])

    def test_public_procurement_cannot_be_emailed(self):
        notice = {"kind": "b2b", "company": "Prefeitura Exemplo",
                  "title": "Hospedagem Cloud", "notice_id": "32/2026",
                  "origin_type": "public_procurement"}
        result = preflight(
            notice, [], channel="gmail", source_verified=True,
            recipient_verified=True, history_checked=True, demand_verified=True,
        )
        self.assertFalse(result["ready"])
        self.assertTrue(any("canal oficial" in x for x in result["blockers"]))

    def test_record_requires_proof_and_prevents_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            tracker = Path(folder, "tracker.jsonl")
            cv = Path(folder, "cv.pdf")
            cv.write_bytes(b"mock pdf")
            with self.assertRaisesRegex(ValueError, "comprovante"):
                record_event(tracker, JOB, "sent", attachment=str(cv))
            record_event(tracker, JOB, "sent", receipt="outlook:abc",
                         attachment=str(cv), source="LinkedIn")
            events = load_events(tracker)
            self.assertEqual(len(events), 1)
            self.assertIsNotNone(duplicate_of(
                {**JOB, "url": "https://careers.example.org/jobs/17?utm_campaign=x"},
                events,
            ))
            with self.assertRaisesRegex(ValueError, "já registrado"):
                record_event(tracker, JOB, "sent", receipt="outlook:xyz",
                             attachment=str(cv))

    def test_distinct_job_ids_are_not_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            tracker = Path(folder, "events.jsonl")
            cv = Path(folder, "cv.pdf")
            cv.write_bytes(b"abc")
            record_event(tracker, JOB, "sent", receipt="m1", attachment=str(cv))
            other = {**JOB, "job_id": "SRE-2026-18",
                     "url": "https://careers.example.org/jobs/18"}
            self.assertIsNone(duplicate_of(other, load_events(tracker)))
            self.assertNotEqual(opportunity_key(JOB), opportunity_key(other))

    def test_metrics_unique_application_and_source(self):
        with tempfile.TemporaryDirectory() as folder:
            tracker = Path(folder, "events.jsonl")
            cv = Path(folder, "cv.pdf")
            cv.write_bytes(b"abc")
            record_event(tracker, JOB, "sent", receipt="m1",
                         attachment=str(cv), source="LinkedIn")
            record_event(tracker, JOB, "interview", source="LinkedIn")
            result = metrics(load_events(tracker))
            self.assertEqual(result["job_applications"], 1)
            self.assertEqual(result["interviews"], 1)
            self.assertEqual(result["interview_rate"], 1.0)
            self.assertEqual(result["applications_by_source"]["LinkedIn"], 1)


if __name__ == "__main__":
    unittest.main()
