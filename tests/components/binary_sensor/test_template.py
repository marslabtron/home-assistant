"""The tests for the Template Binary sensor platform."""
import asyncio
from datetime import timedelta
import unittest
from unittest import mock

from homeassistant.core import CoreState, State
from homeassistant.const import MATCH_ALL
from homeassistant import setup
from homeassistant.components.binary_sensor import template
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import template as template_hlpr
from homeassistant.util.async import run_callback_threadsafe
import homeassistant.util.dt as dt_util
from homeassistant.helpers.restore_state import DATA_RESTORE_CACHE

from tests.common import (
    get_test_home_assistant, assert_setup_component, mock_component,
    async_fire_time_changed)


class TestBinarySensorTemplate(unittest.TestCase):
    """Test for Binary sensor template platform."""

    hass = None
    # pylint: disable=invalid-name

    def setup_method(self, method):
        """Setup things to be run when tests are started."""
        self.hass = get_test_home_assistant()

    def teardown_method(self, method):
        """Stop everything that was started."""
        self.hass.stop()

    def test_setup(self):
        """"Test the setup."""
        config = {
            'binary_sensor': {
                'platform': 'template',
                'sensors': {
                    'test': {
                        'friendly_name': 'virtual thingy',
                        'value_template': '{{ foo }}',
                        'device_class': 'motion',
                    },
                },
            },
        }
        with assert_setup_component(1):
            assert setup.setup_component(
                self.hass, 'binary_sensor', config)

    def test_setup_no_sensors(self):
        """"Test setup with no sensors."""
        with assert_setup_component(0):
            assert setup.setup_component(self.hass, 'binary_sensor', {
                'binary_sensor': {
                    'platform': 'template'
                }
            })

    def test_setup_invalid_device(self):
        """"Test the setup with invalid devices."""
        with assert_setup_component(0):
            assert setup.setup_component(self.hass, 'binary_sensor', {
                'binary_sensor': {
                    'platform': 'template',
                    'sensors': {
                        'foo bar': {},
                    },
                }
            })

    def test_setup_invalid_device_class(self):
        """"Test setup with invalid sensor class."""
        with assert_setup_component(0):
            assert setup.setup_component(self.hass, 'binary_sensor', {
                'binary_sensor': {
                    'platform': 'template',
                    'sensors': {
                        'test': {
                            'value_template': '{{ foo }}',
                            'device_class': 'foobarnotreal',
                        },
                    },
                }
            })

    def test_setup_invalid_missing_template(self):
        """"Test setup with invalid and missing template."""
        with assert_setup_component(0):
            assert setup.setup_component(self.hass, 'binary_sensor', {
                'binary_sensor': {
                    'platform': 'template',
                    'sensors': {
                        'test': {
                            'device_class': 'motion',
                        },
                    }
                }
            })

    def test_attributes(self):
        """"Test the attributes."""
        vs = run_callback_threadsafe(
            self.hass.loop, template.BinarySensorTemplate,
            self.hass, 'parent', 'Parent', 'motion',
            template_hlpr.Template('{{ 1 > 1 }}', self.hass), MATCH_ALL,
            None, None
        ).result()
        self.assertFalse(vs.should_poll)
        self.assertEqual('motion', vs.device_class)
        self.assertEqual('Parent', vs.name)

        run_callback_threadsafe(self.hass.loop, vs.async_check_state).result()
        self.assertFalse(vs.is_on)

        # pylint: disable=protected-access
        vs._template = template_hlpr.Template("{{ 2 > 1 }}", self.hass)

        run_callback_threadsafe(self.hass.loop, vs.async_check_state).result()
        self.assertTrue(vs.is_on)

    def test_event(self):
        """"Test the event."""
        config = {
            'binary_sensor': {
                'platform': 'template',
                'sensors': {
                    'test': {
                        'friendly_name': 'virtual thingy',
                        'value_template':
                            "{{ states.sensor.test_state.state == 'on' }}",
                        'device_class': 'motion',
                    },
                },
            },
        }
        with assert_setup_component(1):
            assert setup.setup_component(
                self.hass, 'binary_sensor', config)

        self.hass.start()
        self.hass.block_till_done()

        state = self.hass.states.get('binary_sensor.test')
        assert state.state == 'off'

        self.hass.states.set('sensor.test_state', 'on')
        self.hass.block_till_done()

        state = self.hass.states.get('binary_sensor.test')
        assert state.state == 'on'

    @mock.patch('homeassistant.helpers.template.Template.render')
    def test_update_template_error(self, mock_render):
        """"Test the template update error."""
        vs = run_callback_threadsafe(
            self.hass.loop, template.BinarySensorTemplate,
            self.hass, 'parent', 'Parent', 'motion',
            template_hlpr.Template('{{ 1 > 1 }}', self.hass), MATCH_ALL,
            None, None
        ).result()
        mock_render.side_effect = TemplateError('foo')
        run_callback_threadsafe(self.hass.loop, vs.async_check_state).result()
        mock_render.side_effect = TemplateError(
            "UndefinedError: 'None' has no attribute")
        run_callback_threadsafe(self.hass.loop, vs.async_check_state).result()


@asyncio.coroutine
def test_restore_state(hass):
    """Ensure states are restored on startup."""
    hass.data[DATA_RESTORE_CACHE] = {
        'binary_sensor.test': State('binary_sensor.test', 'on'),
    }

    hass.state = CoreState.starting
    mock_component(hass, 'recorder')

    config = {
        'binary_sensor': {
            'platform': 'template',
            'sensors': {
                'test': {
                    'friendly_name': 'virtual thingy',
                    'value_template':
                        "{{ states.sensor.test_state.state == 'on' }}",
                    'device_class': 'motion',
                },
            },
        },
    }
    yield from setup.async_setup_component(hass, 'binary_sensor', config)

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'on'

    yield from hass.async_start()
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'off'


@asyncio.coroutine
def test_template_delay_on(hass):
    """Test binary sensor template delay on."""
    config = {
        'binary_sensor': {
            'platform': 'template',
            'sensors': {
                'test': {
                    'friendly_name': 'virtual thingy',
                    'value_template':
                        "{{ states.sensor.test_state.state == 'on' }}",
                    'device_class': 'motion',
                    'delay_on': 5
                },
            },
        },
    }
    yield from setup.async_setup_component(hass, 'binary_sensor', config)
    yield from hass.async_start()

    hass.states.async_set('sensor.test_state', 'on')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'off'

    future = dt_util.utcnow() + timedelta(seconds=5)
    async_fire_time_changed(hass, future)
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'on'

    # check with time changes
    hass.states.async_set('sensor.test_state', 'off')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'off'

    hass.states.async_set('sensor.test_state', 'on')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'off'

    hass.states.async_set('sensor.test_state', 'off')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'off'

    future = dt_util.utcnow() + timedelta(seconds=5)
    async_fire_time_changed(hass, future)
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'off'


@asyncio.coroutine
def test_template_delay_off(hass):
    """Test binary sensor template delay off."""
    config = {
        'binary_sensor': {
            'platform': 'template',
            'sensors': {
                'test': {
                    'friendly_name': 'virtual thingy',
                    'value_template':
                        "{{ states.sensor.test_state.state == 'on' }}",
                    'device_class': 'motion',
                    'delay_off': 5
                },
            },
        },
    }
    hass.states.async_set('sensor.test_state', 'on')
    yield from setup.async_setup_component(hass, 'binary_sensor', config)
    yield from hass.async_start()

    hass.states.async_set('sensor.test_state', 'off')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'on'

    future = dt_util.utcnow() + timedelta(seconds=5)
    async_fire_time_changed(hass, future)
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'off'

    # check with time changes
    hass.states.async_set('sensor.test_state', 'on')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'on'

    hass.states.async_set('sensor.test_state', 'off')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'on'

    hass.states.async_set('sensor.test_state', 'on')
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'on'

    future = dt_util.utcnow() + timedelta(seconds=5)
    async_fire_time_changed(hass, future)
    yield from hass.async_block_till_done()

    state = hass.states.get('binary_sensor.test')
    assert state.state == 'on'
