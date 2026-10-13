"""Read-only unittest receipts; canonical -m unittest command stays unchanged."""
import atexit
import json
import os
from pathlib import Path
import unittest

_receipt = os.environ.get('QUALIFICATION_UNITTEST_RECEIPT')
if _receipt:
    _rows = []
    _original = unittest.TextTestResult

    class QualificationResult(_original):
        def startTest(self, test):
            _rows.append({'event': 'start', 'id': test.id()})
            super().startTest(test)

        def _record(self, test, outcome, detail=None):
            _rows.append({'event': 'outcome', 'id': test.id(),
                          'outcome': outcome, 'detail': detail})

        def addSuccess(self, test):
            self._record(test, 'pass')
            super().addSuccess(test)

        def addFailure(self, test, err):
            self._record(test, 'fail')
            super().addFailure(test, err)

        def addError(self, test, err):
            self._record(test, 'error')
            super().addError(test, err)

        def addSkip(self, test, reason):
            self._record(test, 'skip', reason)
            super().addSkip(test, reason)

        def addExpectedFailure(self, test, err):
            self._record(test, 'expected_failure')
            super().addExpectedFailure(test, err)

        def addUnexpectedSuccess(self, test):
            self._record(test, 'unexpected_success')
            super().addUnexpectedSuccess(test)

        def addSubTest(self, test, subtest, err):
            outcome = 'pass' if err is None else (
                'fail' if issubclass(err[0], test.failureException) else 'error')
            _rows.append({'event': 'subtest', 'parent': test.id(),
                          'id': subtest.id(), 'outcome': outcome})
            super().addSubTest(test, subtest, err)

    unittest.TextTestRunner.resultclass = QualificationResult
    unittest.TextTestResult = QualificationResult

    @atexit.register
    def save_receipt():
        Path(_receipt).write_text(json.dumps({'rows': _rows}, indent=2) + '\n',
                                 encoding='utf-8')
