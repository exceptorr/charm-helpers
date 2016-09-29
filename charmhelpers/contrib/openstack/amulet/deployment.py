# Copyright 2014-2015 Canonical Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import re
import sys
import six
from collections import OrderedDict
from charmhelpers.contrib.amulet.deployment import (
    AmuletDeployment
)

DEBUG = logging.DEBUG
ERROR = logging.ERROR


class OpenStackAmuletDeployment(AmuletDeployment):
    """OpenStack amulet deployment.

       This class inherits from AmuletDeployment and has additional support
       that is specifically for use by OpenStack charms.
       """

    def __init__(self, series=None, openstack=None, source=None,
                 stable=True, log_level=DEBUG):
        """Initialize the deployment environment."""
        super(OpenStackAmuletDeployment, self).__init__(series)
        self.log = self.get_logger(level=log_level)
        self.log.info('OpenStackAmuletDeployment:  init')
        self.openstack = openstack
        self.source = source
        self.stable = stable

    def get_logger(self, name="deployment-logger", level=logging.DEBUG):
        """Get a logger object that will log to stdout."""
        log = logging
        logger = log.getLogger(name)
        fmt = log.Formatter("%(asctime)s %(funcName)s "
                            "%(levelname)s: %(message)s")

        handler = log.StreamHandler(stream=sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(fmt)

        logger.addHandler(handler)
        logger.setLevel(level)

        return logger

    def _determine_branch_locations(self, other_services):
        """Determine the branch locations for the other services.

           Determine if the local branch being tested is derived from its
           stable or next (dev) branch, and based on this, use the corresonding
           stable or next branches for the other_services."""

        self.log.info('OpenStackAmuletDeployment:  determine branch locations')

        # Charms outside the ~openstack-charmers
        base_charms = {
            'mysql': ['precise', 'trusty'],
            'mongodb': ['precise', 'trusty'],
            'nrpe': ['precise', 'trusty', 'wily', 'xenial'],
        }

        for svc in other_services:
            # If a location has been explicitly set, use it
            if svc.get('location'):
                continue
            if svc['name'] in base_charms:
                # NOTE: not all charms have support for all series we
                #       want/need to test against, so fix to most recent
                #       that each base charm supports
                target_series = self.series
                if self.series not in base_charms[svc['name']]:
                    target_series = base_charms[svc['name']][-1]
                svc['location'] = 'cs:{}/{}'.format(target_series,
                                                    svc['name'])
            elif self.stable:
                svc['location'] = 'cs:{}/{}'.format(self.series,
                                                    svc['name'])
            else:
                svc['location'] = 'cs:~openstack-charmers-next/{}/{}'.format(
                    self.series,
                    svc['name']
                )

        return other_services

    def _add_services(self, this_service, other_services, use_source=None,
                      no_origin=None):
        """Add services to the deployment and optionally set
        openstack-origin/source.

        :param this_service dict: Service dictionary describing the service
                                  whose amulet tests are being run
        :param other_services dict: List of service dictionaries describing
                                    the services needed to support the target
                                    service
        :param use_source list: List of services which use the 'source' config
                                option rather than 'openstack-origin'
        :param no_origin list: List of services which do not support setting
                               the Cloud Archive.
        Service Dict:
            {
                'name': str charm-name,
                'units': int number of units,
                'constraints': dict of juju constraints,
                'location': str location of charm,
            }
        eg
        this_service = {
            'name': 'openvswitch-odl',
            'constraints': {'mem': '8G'},
        }
        other_services = [
            {
                'name': 'nova-compute',
                'units': 2,
                'constraints': {'mem': '4G'},
                'location': cs:~bob/xenial/nova-compute
            },
            {
                'name': 'mysql',
                'constraints': {'mem': '2G'},
            },
            {'neutron-api-odl'}]
        use_source = ['mysql']
        no_origin = ['neutron-api-odl']
        """
        self.log.info('OpenStackAmuletDeployment:  adding services')

        other_services = self._determine_branch_locations(other_services)

        super(OpenStackAmuletDeployment, self)._add_services(this_service,
                                                             other_services)

        services = other_services
        services.append(this_service)

        # Charms which should use the source config option
        if not use_source:
            use_source = ['mysql', 'mongodb', 'rabbitmq-server', 'ceph',
                          'ceph-osd', 'ceph-radosgw', 'ceph-mon', 'ceph-proxy']

        # Charms which can not use openstack-origin, ie. many subordinates
        if not no_origin:
            no_origin = ['cinder-ceph', 'hacluster', 'neutron-openvswitch',
                         'nrpe', 'openvswitch-odl', 'neutron-api-odl',
                         'odl-controller', 'cinder-backup', 'nexentaedge-data',
                         'nexentaedge-iscsi-gw', 'nexentaedge-swift-gw',
                         'cinder-nexentaedge', 'nexentaedge-mgmt']

        if self.openstack:
            for svc in services:
                if svc['name'] not in use_source + no_origin:
                    config = {'openstack-origin': self.openstack}
                    self.d.configure(svc['name'], config)

        if self.source:
            for svc in services:
                if svc['name'] in use_source and svc['name'] not in no_origin:
                    config = {'source': self.source}
                    self.d.configure(svc['name'], config)

    def _configure_services(self, configs):
        """Configure all of the services."""
        self.log.info('OpenStackAmuletDeployment:  configure services')
        for service, config in six.iteritems(configs):
            self.d.configure(service, config)

    def _auto_wait_for_status(self, message=None, exclude_services=None,
                              include_only=None, timeout=1800):
        """Wait for all units to have a specific extended status, except
        for any defined as excluded.  Unless specified via message, any
        status containing any case of 'ready' will be considered a match.

        Examples of message usage:

          Wait for all unit status to CONTAIN any case of 'ready' or 'ok':
              message = re.compile('.*ready.*|.*ok.*', re.IGNORECASE)

          Wait for all units to reach this status (exact match):
              message = re.compile('^Unit is ready and clustered$')

          Wait for all units to reach any one of these (exact match):
              message = re.compile('Unit is ready|OK|Ready')

          Wait for at least one unit to reach this status (exact match):
              message = {'ready'}

        See Amulet's sentry.wait_for_messages() for message usage detail.
        https://github.com/juju/amulet/blob/master/amulet/sentry.py

        :param message: Expected status match
        :param exclude_services: List of juju service names to ignore,
            not to be used in conjuction with include_only.
        :param include_only: List of juju service names to exclusively check,
            not to be used in conjuction with exclude_services.
        :param timeout: Maximum time in seconds to wait for status match
        :returns: None.  Raises if timeout is hit.
        """
        self.log.info('Waiting for extended status on units...')

        all_services = self.d.services.keys()

        if exclude_services and include_only:
            raise ValueError('exclude_services can not be used '
                             'with include_only')

        if message:
            if isinstance(message, re._pattern_type):
                match = message.pattern
            else:
                match = message

            self.log.debug('Custom extended status wait match: '
                           '{}'.format(match))
        else:
            self.log.debug('Default extended status wait match:  contains '
                           'READY (case-insensitive)')
            message = re.compile('.*ready.*', re.IGNORECASE)

        if exclude_services:
            self.log.debug('Excluding services from extended status match: '
                           '{}'.format(exclude_services))
        else:
            exclude_services = []

        if include_only:
            services = include_only
        else:
            services = list(set(all_services) - set(exclude_services))

        self.log.debug('Waiting up to {}s for extended status on services: '
                       '{}'.format(timeout, services))
        service_messages = {service: message for service in services}
        self.d.sentry.wait_for_messages(service_messages, timeout=timeout)
        self.log.info('OK')

    def _get_openstack_release(self):
        """Get openstack release.

           Return an integer representing the enum value of the openstack
           release.
           """
        # Must be ordered by OpenStack release (not by Ubuntu release):
        (self.precise_essex, self.precise_folsom, self.precise_grizzly,
         self.precise_havana, self.precise_icehouse,
         self.trusty_icehouse, self.trusty_juno, self.utopic_juno,
         self.trusty_kilo, self.vivid_kilo, self.trusty_liberty,
         self.wily_liberty, self.trusty_mitaka,
         self.xenial_mitaka, self.xenial_newton,
         self.yakkety_newton) = range(16)

        releases = {
            ('precise', None): self.precise_essex,
            ('precise', 'cloud:precise-folsom'): self.precise_folsom,
            ('precise', 'cloud:precise-grizzly'): self.precise_grizzly,
            ('precise', 'cloud:precise-havana'): self.precise_havana,
            ('precise', 'cloud:precise-icehouse'): self.precise_icehouse,
            ('trusty', None): self.trusty_icehouse,
            ('trusty', 'cloud:trusty-juno'): self.trusty_juno,
            ('trusty', 'cloud:trusty-kilo'): self.trusty_kilo,
            ('trusty', 'cloud:trusty-liberty'): self.trusty_liberty,
            ('trusty', 'cloud:trusty-mitaka'): self.trusty_mitaka,
            ('utopic', None): self.utopic_juno,
            ('vivid', None): self.vivid_kilo,
            ('wily', None): self.wily_liberty,
            ('xenial', None): self.xenial_mitaka,
            ('xenial', 'cloud:xenial-newton'): self.xenial_newton,
            ('yakkety', None): self.yakkety_newton,
        }
        return releases[(self.series, self.openstack)]

    def _get_openstack_release_string(self):
        """Get openstack release string.

           Return a string representing the openstack release.
           """
        releases = OrderedDict([
            ('precise', 'essex'),
            ('quantal', 'folsom'),
            ('raring', 'grizzly'),
            ('saucy', 'havana'),
            ('trusty', 'icehouse'),
            ('utopic', 'juno'),
            ('vivid', 'kilo'),
            ('wily', 'liberty'),
            ('xenial', 'mitaka'),
            ('yakkety', 'newton'),
        ])
        if self.openstack:
            os_origin = self.openstack.split(':')[1]
            return os_origin.split('%s-' % self.series)[1].split('/')[0]
        else:
            return releases[self.series]

    def get_ceph_expected_pools(self, radosgw=False):
        """Return a list of expected ceph pools in a ceph + cinder + glance
        test scenario, based on OpenStack release and whether ceph radosgw
        is flagged as present or not."""

        if self._get_openstack_release() >= self.trusty_kilo:
            # Kilo or later
            pools = [
                'rbd',
                'cinder',
                'glance'
            ]
        else:
            # Juno or earlier
            pools = [
                'data',
                'metadata',
                'rbd',
                'cinder',
                'glance'
            ]

        if radosgw:
            pools.extend([
                '.rgw.root',
                '.rgw.control',
                '.rgw',
                '.rgw.gc',
                '.users.uid'
            ])

        return pools
