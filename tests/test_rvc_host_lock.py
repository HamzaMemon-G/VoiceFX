import os
import sys
from pathlib import Path
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from voice_session_lock import VoiceSessionLock, SESSION_MUTEX


@unittest.skipUnless(os.name == 'nt', 'Windows named session admission')
class LockContracts(unittest.TestCase):
    def test_duplicate_rejected_then_release_allows_fresh_session(self):
        name = 'Local\\VoiceFX.Test.' + uuid.uuid4().hex
        with VoiceSessionLock(name):
            with self.assertRaisesRegex(RuntimeError, 'Another VoiceFX'):
                with VoiceSessionLock(name):
                    self.fail('duplicate admitted')
        with VoiceSessionLock(name):
            pass
        self.assertEqual(SESSION_MUTEX, 'Local\\VoiceFX.Stream')

    def test_exception_releases_admission(self):
        name = 'Local\\VoiceFX.Test.' + uuid.uuid4().hex
        with self.assertRaises(ValueError):
            with VoiceSessionLock(name):
                raise ValueError('driver failure')
        with VoiceSessionLock(name):
            pass

if __name__ == '__main__':
    unittest.main()
