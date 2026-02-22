"""Tests for Lcore enhanced config system."""

import unittest
import os
import json
import tempfile
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import ConfigDict


# ---------------------------------------------------------------------------
# Schema dataclasses used by validate_config tests
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    debug: bool = False
    port: int = 8080
    db_host: str = 'localhost'  # maps to config key 'db.host'


@dataclass
class StrictConfig:
    """Schema with a required field (no default value)."""
    api_key: str = field(default_factory=lambda: (_ for _ in ()).throw(TypeError))

    # Use a sentinel to indicate "required" by not providing a default
    # Actually, dataclasses.MISSING is checked internally, so we just need
    # a field with no default at all.


# Simpler required-field schema using positional-only field (no default)
@dataclass
class RequiredFieldConfig:
    secret_key: str  # required, no default -> maps to config key 'secret.key'
    debug: bool = False


# ---------------------------------------------------------------------------
# Tests for load_env
# ---------------------------------------------------------------------------

class TestLoadEnv(unittest.TestCase):
    """Test ConfigDict.load_env() behaviour."""

    def setUp(self):
        os.environ['LCORE_DEBUG'] = 'true'
        os.environ['LCORE_DB__HOST'] = 'localhost'
        os.environ['LCORE_DB__PORT'] = '5432'

    def tearDown(self):
        os.environ.pop('LCORE_DEBUG', None)
        os.environ.pop('LCORE_DB__HOST', None)
        os.environ.pop('LCORE_DB__PORT', None)

    def test_load_env_loads_matching_vars(self):
        """load_env should populate the config from matching env vars."""
        config = ConfigDict()
        config.load_env(prefix='LCORE_')
        self.assertIn('debug', config)
        self.assertEqual(config['debug'], 'true')

    def test_load_env_strip_prefix_true(self):
        """With strip_prefix=True the LCORE_ prefix is removed from keys."""
        config = ConfigDict()
        config.load_env(prefix='LCORE_', strip_prefix=True)
        # Keys should NOT contain the prefix
        self.assertIn('debug', config)
        self.assertNotIn('lcore_debug', config)

    def test_load_env_strip_prefix_false(self):
        """With strip_prefix=False the full env var name is kept (lowered)."""
        config = ConfigDict()
        config.load_env(prefix='LCORE_', strip_prefix=False)
        self.assertIn('lcore_debug', config)
        self.assertNotIn('debug', config)

    def test_load_env_double_underscore_to_dot(self):
        """Double underscores in env var names become dot-separated keys."""
        config = ConfigDict()
        config.load_env(prefix='LCORE_', strip_prefix=True)
        self.assertIn('db.host', config)
        self.assertEqual(config['db.host'], 'localhost')
        self.assertIn('db.port', config)
        self.assertEqual(config['db.port'], '5432')

    def test_load_env_ignores_non_matching_prefix(self):
        """Env vars that do not start with the prefix are ignored."""
        os.environ['OTHER_VAR'] = 'should_not_appear'
        try:
            config = ConfigDict()
            config.load_env(prefix='LCORE_')
            self.assertNotIn('other_var', config)
            self.assertNotIn('OTHER_VAR', config)
        finally:
            os.environ.pop('OTHER_VAR', None)

    def test_load_env_returns_self(self):
        """load_env returns the ConfigDict for chaining."""
        config = ConfigDict()
        result = config.load_env(prefix='LCORE_')
        self.assertIs(result, config)


# ---------------------------------------------------------------------------
# Tests for load_json
# ---------------------------------------------------------------------------

class TestLoadJson(unittest.TestCase):
    """Test ConfigDict.load_json() behaviour."""

    def test_load_json_flat(self):
        """load_json loads flat key/value pairs from a JSON file."""
        data = {'debug': True, 'port': 8080}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            config = ConfigDict()
            config.load_json(fname)
            self.assertEqual(config['debug'], True)
            self.assertEqual(config['port'], 8080)
        finally:
            os.unlink(fname)

    def test_load_json_nested(self):
        """Nested dicts in JSON become dot-separated namespace keys."""
        data = {'db': {'host': 'localhost', 'port': 5432}}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            config = ConfigDict()
            config.load_json(fname)
            self.assertEqual(config['db.host'], 'localhost')
            self.assertEqual(config['db.port'], 5432)
        finally:
            os.unlink(fname)

    def test_load_json_deeply_nested(self):
        """Deeply nested dicts produce multi-level dot keys."""
        data = {'app': {'db': {'connection': {'timeout': 30}}}}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            config = ConfigDict()
            config.load_json(fname)
            self.assertEqual(config['app.db.connection.timeout'], 30)
        finally:
            os.unlink(fname)

    def test_load_json_returns_self(self):
        """load_json returns the ConfigDict for chaining."""
        data = {'key': 'value'}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            config = ConfigDict()
            result = config.load_json(fname)
            self.assertIs(result, config)
        finally:
            os.unlink(fname)

    def test_load_json_file_not_found(self):
        """load_json raises an error when the file does not exist."""
        config = ConfigDict()
        with self.assertRaises(FileNotFoundError):
            config.load_json('/tmp/nonexistent_config_file_abc123.json')


# ---------------------------------------------------------------------------
# Tests for load_dotenv
# ---------------------------------------------------------------------------

class TestLoadDotenv(unittest.TestCase):
    """Test ConfigDict.load_dotenv() behaviour."""

    def _write_env_file(self, content):
        """Helper: write content to a temp .env file and return the path."""
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.env', delete=False
        )
        f.write(content)
        f.close()
        return f.name

    def test_load_dotenv_sets_env_vars(self):
        """load_dotenv should set environment variables from the file."""
        fname = self._write_env_file('MY_TEST_VAR_1=hello\nMY_TEST_VAR_2=world\n')
        # Make sure they are not already set
        os.environ.pop('MY_TEST_VAR_1', None)
        os.environ.pop('MY_TEST_VAR_2', None)
        try:
            config = ConfigDict()
            config.load_dotenv(fname)
            self.assertEqual(os.environ.get('MY_TEST_VAR_1'), 'hello')
            self.assertEqual(os.environ.get('MY_TEST_VAR_2'), 'world')
        finally:
            os.environ.pop('MY_TEST_VAR_1', None)
            os.environ.pop('MY_TEST_VAR_2', None)
            os.unlink(fname)

    def test_load_dotenv_does_not_overwrite_existing(self):
        """Existing env vars must not be overwritten (uses setdefault)."""
        os.environ['MY_EXISTING_VAR'] = 'original'
        fname = self._write_env_file('MY_EXISTING_VAR=overwritten\n')
        try:
            config = ConfigDict()
            config.load_dotenv(fname)
            self.assertEqual(os.environ['MY_EXISTING_VAR'], 'original')
        finally:
            os.environ.pop('MY_EXISTING_VAR', None)
            os.unlink(fname)

    def test_load_dotenv_skips_comments_and_blanks(self):
        """Lines starting with # and blank lines are ignored."""
        content = (
            '# This is a comment\n'
            '\n'
            'DOTENV_REAL_KEY=value\n'
            '   \n'
            '# Another comment\n'
        )
        fname = self._write_env_file(content)
        os.environ.pop('DOTENV_REAL_KEY', None)
        try:
            config = ConfigDict()
            config.load_dotenv(fname)
            self.assertEqual(os.environ.get('DOTENV_REAL_KEY'), 'value')
        finally:
            os.environ.pop('DOTENV_REAL_KEY', None)
            os.unlink(fname)

    def test_load_dotenv_strips_quotes(self):
        """Surrounding double or single quotes on values are stripped."""
        content = (
            'QUOTED_DOUBLE="double_val"\n'
            "QUOTED_SINGLE='single_val'\n"
        )
        fname = self._write_env_file(content)
        os.environ.pop('QUOTED_DOUBLE', None)
        os.environ.pop('QUOTED_SINGLE', None)
        try:
            config = ConfigDict()
            config.load_dotenv(fname)
            self.assertEqual(os.environ.get('QUOTED_DOUBLE'), 'double_val')
            self.assertEqual(os.environ.get('QUOTED_SINGLE'), 'single_val')
        finally:
            os.environ.pop('QUOTED_DOUBLE', None)
            os.environ.pop('QUOTED_SINGLE', None)
            os.unlink(fname)

    def test_load_dotenv_missing_file_returns_self(self):
        """If the .env file does not exist, load_dotenv returns self silently."""
        config = ConfigDict()
        result = config.load_dotenv('/tmp/definitely_does_not_exist.env')
        self.assertIs(result, config)

    def test_load_dotenv_returns_self(self):
        """load_dotenv returns the ConfigDict for chaining."""
        fname = self._write_env_file('CHAIN_VAR=1\n')
        os.environ.pop('CHAIN_VAR', None)
        try:
            config = ConfigDict()
            result = config.load_dotenv(fname)
            self.assertIs(result, config)
        finally:
            os.environ.pop('CHAIN_VAR', None)
            os.unlink(fname)


# ---------------------------------------------------------------------------
# Tests for validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig(unittest.TestCase):
    """Test ConfigDict.validate_config() behaviour."""

    def test_valid_config_passes(self):
        """No error when all keys match the schema and types are correct."""
        config = ConfigDict()
        config['debug'] = False
        config['port'] = 8080
        config['db.host'] = 'localhost'
        # Should not raise
        result = config.validate_config(AppConfig)
        self.assertIs(result, config)

    def test_defaults_fill_missing_optional_fields(self):
        """Fields with defaults are not required in the config."""
        config = ConfigDict()
        # AppConfig has defaults for all fields, so an empty config is fine
        config.validate_config(AppConfig)

    def test_missing_required_field_raises_value_error(self):
        """A required field (no default) missing from config raises ValueError."""
        config = ConfigDict()
        # RequiredFieldConfig needs 'secret.key' (secret_key -> secret.key)
        with self.assertRaises(ValueError) as ctx:
            config.validate_config(RequiredFieldConfig)
        self.assertIn('secret.key', str(ctx.exception))

    def test_type_mismatch_auto_converts_string_to_int(self):
        """String values are auto-converted to the expected int type."""
        config = ConfigDict()
        config['port'] = '9090'  # string, schema expects int
        config.validate_config(AppConfig)
        self.assertEqual(config['port'], 9090)
        self.assertIsInstance(config['port'], int)

    def test_type_mismatch_auto_converts_string_to_bool(self):
        """String 'true'/'1'/'yes' are auto-converted to bool True."""
        for truthy in ('true', '1', 'yes', 'True', 'YES'):
            config = ConfigDict()
            config['debug'] = truthy
            config.validate_config(AppConfig)
            self.assertIs(config['debug'], True,
                          msg='Expected True for %r' % truthy)

    def test_type_mismatch_auto_converts_string_to_bool_false(self):
        """String values not in ('true','1','yes') convert to bool False."""
        for falsy in ('false', '0', 'no', 'anything_else'):
            config = ConfigDict()
            config['debug'] = falsy
            config.validate_config(AppConfig)
            self.assertIs(config['debug'], False,
                          msg='Expected False for %r' % falsy)

    def test_type_mismatch_auto_converts_string_to_float(self):
        """String values are auto-converted to float when schema expects it."""
        @dataclass
        class FloatConfig:
            rate: float = 1.0

        config = ConfigDict()
        config['rate'] = '3.14'
        config.validate_config(FloatConfig)
        self.assertAlmostEqual(config['rate'], 3.14)
        self.assertIsInstance(config['rate'], float)

    def test_non_dataclass_raises_type_error(self):
        """Passing a non-dataclass schema raises TypeError."""
        config = ConfigDict()

        with self.assertRaises(TypeError) as ctx:
            config.validate_config(dict)
        self.assertIn('dataclass', str(ctx.exception).lower())

    def test_non_dataclass_plain_class_raises_type_error(self):
        """A plain class (not a dataclass) raises TypeError."""
        class PlainSchema:
            debug: bool = False

        config = ConfigDict()
        with self.assertRaises(TypeError):
            config.validate_config(PlainSchema)

    def test_validate_underscore_to_dot_mapping(self):
        """Field name underscores are mapped to dots in config keys."""
        config = ConfigDict()
        config['db.host'] = '10.0.0.1'
        # AppConfig.db_host -> 'db.host'
        config.validate_config(AppConfig)
        self.assertEqual(config['db.host'], '10.0.0.1')

    def test_validate_returns_self(self):
        """validate_config returns the ConfigDict for chaining."""
        config = ConfigDict()
        result = config.validate_config(AppConfig)
        self.assertIs(result, config)

    def test_unconvertible_type_raises_value_error(self):
        """A value that cannot be converted to the target type raises ValueError."""
        config = ConfigDict()
        config['port'] = 'not_a_number'
        with self.assertRaises(ValueError) as ctx:
            config.validate_config(AppConfig)
        self.assertIn('port', str(ctx.exception))


# ---------------------------------------------------------------------------
# Integration-style tests combining multiple enhanced features
# ---------------------------------------------------------------------------

class TestEnhancedConfigIntegration(unittest.TestCase):
    """Integration tests combining load_env, load_json, and validate_config."""

    def test_load_env_then_validate(self):
        """Load from env vars and then validate against a schema."""
        os.environ['MYAPP_DEBUG'] = 'true'
        os.environ['MYAPP_PORT'] = '3000'
        os.environ['MYAPP_DB__HOST'] = '10.0.0.5'
        try:
            config = ConfigDict()
            config.load_env(prefix='MYAPP_', strip_prefix=True)
            config.validate_config(AppConfig)
            self.assertIs(config['debug'], True)
            self.assertEqual(config['port'], 3000)
            self.assertEqual(config['db.host'], '10.0.0.5')
        finally:
            os.environ.pop('MYAPP_DEBUG', None)
            os.environ.pop('MYAPP_PORT', None)
            os.environ.pop('MYAPP_DB__HOST', None)

    def test_load_json_then_validate(self):
        """Load from a JSON file and then validate against a schema."""
        data = {'debug': 'yes', 'port': '443', 'db': {'host': 'db.example.com'}}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            config = ConfigDict()
            config.load_json(fname)
            config.validate_config(AppConfig)
            self.assertIs(config['debug'], True)
            self.assertEqual(config['port'], 443)
            self.assertEqual(config['db.host'], 'db.example.com')
        finally:
            os.unlink(fname)

    def test_chaining_api(self):
        """All load/validate methods return self, enabling chaining."""
        data = {'port': 8080}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            config = ConfigDict()
            result = config.load_json(fname).validate_config(AppConfig)
            self.assertIs(result, config)
            self.assertEqual(config['port'], 8080)
        finally:
            os.unlink(fname)


if __name__ == '__main__':
    unittest.main()
