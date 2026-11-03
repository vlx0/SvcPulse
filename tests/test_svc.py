"""Classification only. Does not stop or enumerate live services."""

from __future__ import annotations

import unittest

from svcpulse.svc import (
    SERVICE_RUNNING,
    SERVICE_STOPPED,
    START_AUTO,
    START_DEMAND,
    Svc,
    blocked_name,
    can_stop,
    classify,
    session_service,
)


def _svc(name: str, **kw) -> Svc:
    data = dict(display=name, state=SERVICE_STOPPED, start=START_AUTO, accept_stop=False)
    data.update(kw)
    return Svc(name=name, **data)


class ClassifyTests(unittest.TestCase):
    def test_slices(self) -> None:
        rows = [
            _svc("MapsBroker", display="Карты", start=START_AUTO, state=SERVICE_STOPPED, delayed=True),
            _svc("EventTrigger", start=START_AUTO, state=SERVICE_STOPPED, trigger=True),
            _svc("Steam Client Service", display="Steam", start=START_DEMAND, state=SERVICE_RUNNING, accept_stop=True),
            _svc("UserDataSvc_65eea7e", start=START_DEMAND, state=SERVICE_RUNNING, accept_stop=True),
            _svc("Spooler", display="Печать", start=START_AUTO, state=SERVICE_RUNNING, accept_stop=True),
            _svc("RpcSs", start=START_DEMAND, state=SERVICE_RUNNING, accept_stop=True),
        ]
        auto, manual, quiet, session = classify(rows)
        self.assertEqual([s.name for s in auto], ["MapsBroker"])
        self.assertEqual(auto[0].start_text, "авто, отложенный")
        self.assertEqual([s.name for s in manual], ["RpcSs", "Steam Client Service"])
        self.assertEqual(quiet, 1)
        self.assertEqual(session, 1)

    def test_stop_guard(self) -> None:
        self.assertTrue(blocked_name("RpcSs"))
        self.assertTrue(blocked_name("rpcss"))
        self.assertTrue(blocked_name("Appinfo"))
        self.assertTrue(blocked_name("TimeBrokerSvc"))
        self.assertTrue(blocked_name("CDPUserSvc_65eea7e"))
        self.assertFalse(blocked_name("Spooler"))
        self.assertFalse(can_stop(_svc("Appinfo", state=SERVICE_RUNNING, accept_stop=True)))
        self.assertTrue(session_service("NPSMSvc_65eea7e"))
        self.assertFalse(session_service("Spooler"))
        running = _svc("Spooler", state=SERVICE_RUNNING, accept_stop=True)
        self.assertTrue(can_stop(running))
        self.assertFalse(can_stop(_svc("RpcSs", state=SERVICE_RUNNING, accept_stop=True)))
        self.assertFalse(can_stop(_svc("Spooler", state=SERVICE_STOPPED, accept_stop=True)))
        self.assertFalse(can_stop(_svc("Spooler", state=SERVICE_RUNNING, accept_stop=False)))


if __name__ == "__main__":
    unittest.main()
