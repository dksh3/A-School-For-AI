"""Mission 20.1 — validation of the investigation engine's actual behavior.

Each test maps to a numbered behavior from the Mission 20.1 acceptance list:
(1) evidence changes the next action, (2) new leads enter the queue, (3)
referential consistency, (4) explicit failures on invalid input, (5) save/load
preservation, (6) resumability, (7) open questions block unsupported closure,
(8) no repeated questions, (9) report distinguishes classes, (10) stops without
claiming exhaustive discovery.

ALL FIXTURES ARE SYNTHETIC.
"""

from __future__ import annotations

from core.forge.investigate import Investigation


def _case() -> Investigation:
    return Investigation.start("INV-V", "Engine behavior validation", scope="synthetic")


class TestQueueBehavior:
    def test_new_evidence_changes_next_action(self) -> None:
        """(1) Closing the top finding with evidence shifts the queue."""
        case = _case()
        top = case.add_finding("alpha defect", classification="CONFIRMED DEFECT")
        case.add_finding("beta gap", classification="DESIGN GAP", severity="note")
        first = case.next_action()
        assert first is not None and first["target"] == top.id
        ev = case.add_evidence("command", "repro", "exit=1")
        case.attach_evidence(top.id, ev.id)
        case.set_status(top.id, "VERIFIED")
        second = case.next_action()
        assert second is not None
        assert second["target"] != top.id
        assert second["target"] == "F-002"

    def test_new_leads_enter_the_queue(self) -> None:
        """(2) A finding added mid-investigation becomes the next action."""
        case = _case()
        case.add_finding("old lead", classification="DESIGN GAP", severity="note")
        assert case.next_action()["target"] == "F-001"
        lead = case.add_finding(
            "fresh must-fix lead", classification="CONFIRMED DEFECT", severity="must-fix"
        )
        assert case.next_action()["target"] == lead.id


class TestReferentialConsistency:
    def test_attach_evidence_rejects_unknown_ids(self) -> None:
        """(3) Dangling evidence references are refused, not stored."""
        case = _case()
        finding = case.add_finding("probe me", classification="UNKNOWN")
        try:
            case.attach_evidence(finding.id, "E-999")
        except KeyError:
            pass
        else:
            raise AssertionError("dangling evidence id was silently accepted")
        assert not finding.evidence

    def test_link_evidence_rejects_unknown_ids(self) -> None:
        """(3) Hypothesis links to unknown evidence are refused."""
        case = _case()
        hyp = case.add_hypothesis("the cache is wrong")
        try:
            case.link_evidence(hyp.id, "E-404", support=True)
        except KeyError:
            pass
        else:
            raise AssertionError("dangling evidence link was silently accepted")
        assert not hyp.supporting

    def test_attach_evidence_deduplicates(self) -> None:
        """(3) Re-attaching the same evidence does not duplicate the ref."""
        case = _case()
        finding = case.add_finding("probe me", classification="UNKNOWN")
        ev = case.add_evidence("observation", "seen once")
        case.attach_evidence(finding.id, ev.id)
        case.attach_evidence(finding.id, ev.id)
        assert finding.evidence == [ev.id]


class TestExplicitFailures:
    def test_invalid_transitions_and_statuses_fail_explicitly(self) -> None:
        """(4) Unknown statuses, blank justifications, unknown ids raise."""
        case = _case()
        finding = case.add_finding("x", classification="UNKNOWN")
        for bad in ("banana", "verified!", ""):
            try:
                case.set_status(finding.id, bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"status {bad!r} was silently accepted")
        try:
            case.set_status(finding.id, "VERIFIED")
        except ValueError:
            pass
        else:
            raise AssertionError("closing without evidence was allowed")
        try:
            case.set_confidence("H-404", 0.9, "no such hypothesis")
        except KeyError:
            pass
        else:
            raise AssertionError("unknown hypothesis id was accepted")
        hyp = case.add_hypothesis("h")
        try:
            case.set_confidence(hyp.id, 0.9, "   ")
        except ValueError:
            pass
        else:
            raise AssertionError("blank justification was accepted")
        try:
            case.answer_question("Q-404", "a", "e")
        except KeyError:
            pass
        else:
            raise AssertionError("unknown question id was accepted")


class TestPersistence:
    def test_save_load_preserves_state(self) -> None:
        """(5) Evidence, hypotheses, findings, questions, actions survive."""
        case = _case()
        ev = case.add_evidence("command", "repro", "exit=1")
        hyp = case.add_hypothesis("cause is X")
        case.link_evidence(hyp.id, ev.id, support=True)
        case.set_confidence(hyp.id, 0.8, "probe supports it")
        finding = case.add_finding("broken thing", classification="CONFIRMED DEFECT")
        case.attach_evidence(finding.id, ev.id)
        qid = case.record_question("is the flag on?", "changes the fix")
        case.answer_question(qid, "yes", "fix proceeds")
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            case.save(path)
            loaded = Investigation.load(path)
        assert loaded.id == case.id
        assert [e.to_dict() for e in loaded.evidence] == [e.to_dict() for e in case.evidence]
        assert [h.to_dict() for h in loaded.hypotheses] == [
            h.to_dict() for h in case.hypotheses
        ]
        assert [f.to_dict() for f in loaded.findings] == [f.to_dict() for f in case.findings]
        assert loaded.questions == case.questions
        assert loaded.actions == case.actions

    def test_resumed_investigation_continues(self) -> None:
        """(6) A loaded case continues id sequences and the queue."""
        case = _case()
        case.add_evidence("observation", "first")
        case.add_finding("first lead", classification="UNKNOWN")
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            case.save(path)
            resumed = Investigation.load(path)
        ev = resumed.add_evidence("observation", "second")
        assert ev.id == "E-002"
        finding = resumed.add_finding(
            "second lead", classification="CONFIRMED DEFECT", severity="must-fix"
        )
        assert finding.id == "F-002"
        nxt = resumed.next_action()
        assert nxt is not None and nxt["target"] == finding.id


class TestClosureGuards:
    def test_open_question_blocks_unsupported_closure(self) -> None:
        """(7) Findings cannot close without evidence; open questions stay on."""
        case = _case()
        finding = case.add_finding("needs proof", classification="UNKNOWN")
        case.record_question("does the repro pass?", "closes the finding")
        try:
            case.set_status(finding.id, "VERIFIED")
        except ValueError:
            pass
        else:
            raise AssertionError("closure without evidence was allowed")
        nxt = case.next_action()
        assert nxt is not None and nxt["action_kind"] == "ask"
        report = case.to_markdown()
        assert "UNRESOLVED" in report
        assert "affected conclusions are marked BLOCKED" in report

    def test_no_repeated_questions(self) -> None:
        """(8) The same question is never recorded twice, even if answered."""
        case = _case()
        case.record_question("Is the deadline real?", "affects the schedule")
        case.answer_question("Q-001", "yes", "schedule kept")
        for duplicate in ("Is the deadline real?", "  is the deadline REAL?  "):
            try:
                case.record_question(duplicate, "asking again")
            except ValueError:
                pass
            else:
                raise AssertionError(f"duplicate question {duplicate!r} was recorded")
        assert len(case.questions) == 1

    def test_answered_questions_are_not_re_offered(self) -> None:
        """(8) Answered questions leave the open set and the ask queue."""
        case = _case()
        qid = case.record_question("which schema version?", "affects parsing")
        assert case.open_questions()
        case.answer_question(qid, "v2", "parser pinned")
        assert not case.open_questions()
        case.add_finding("done deal", classification="UNKNOWN")
        ev = case.add_evidence("observation", "proof")
        case.attach_evidence("F-001", ev.id)
        case.set_status("F-001", "VERIFIED")
        assert case.next_action() is None


class TestHonestReport:
    def test_report_distinguishes_classes(self) -> None:
        """(9) Confirmed defects, design gaps, unknowns and hypotheses render."""
        case = _case()
        case.add_finding("real bug", classification="CONFIRMED DEFECT")
        case.add_finding("missing wiring", classification="DESIGN GAP", severity="note")
        case.add_finding("odd thing", classification="UNKNOWN", severity="should-fix")
        hyp = case.add_hypothesis("maybe the cache")
        report = case.to_markdown()
        for needle in (
            "CONFIRMED DEFECT",
            "DESIGN GAP",
            "UNKNOWN",
            f"`{hyp.id}` [open]",
            "classification:",
        ):
            assert needle in report, needle

    def test_stops_without_exhaustive_claim(self) -> None:
        """(10) No work left -> no next action; report never claims completeness."""
        case = _case()
        ev = case.add_evidence("observation", "proof")
        finding = case.add_finding("closed", classification="CONFIRMED DEFECT")
        case.attach_evidence(finding.id, ev.id)
        case.set_status(finding.id, "VERIFIED")
        assert case.next_action() is None
        report = case.to_markdown()
        assert "does not claim exhaustive discovery" in report
        assert "Missing evidence is never treated as success" in report
