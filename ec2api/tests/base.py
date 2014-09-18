#    Copyright 2014 Cloudscaling Group, Inc
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import mock
from oslotest import base as test_base

import ec2api.api.apirequest
from ec2api.api import ec2client
from ec2api.tests import fakes
from ec2api.tests import matchers
import ec2api.wsgi


def skip_not_implemented(test_item):
    def decorator(test_item):
        test_item.skip('The feature is not yet implemented')
    return decorator


class ApiTestCase(test_base.BaseTestCase):

    def setUp(self):
        super(ApiTestCase, self).setUp()
        neutron_patcher = mock.patch('neutronclient.v2_0.client.Client')
        self.neutron = neutron_patcher.start().return_value
        self.addCleanup(neutron_patcher.stop)
        nova_servers_patcher = mock.patch('novaclient.v1_1.client.Client')
        self.nova_servers = nova_servers_patcher.start().return_value.servers
        self.addCleanup(nova_servers_patcher.stop)
        db_api_patcher = mock.patch('ec2api.db.api.IMPL')
        self.db_api = db_api_patcher.start()
        self.addCleanup(db_api_patcher.stop)
        ec2_inst_id_to_uuid_patcher = (
            mock.patch('ec2api.api.ec2utils.ec2_inst_id_to_uuid'))
        self.ec2_inst_id_to_uuid = ec2_inst_id_to_uuid_patcher.start()
        self.addCleanup(ec2_inst_id_to_uuid_patcher.stop)
        get_instance_uuid_from_int_id_patcher = (
            mock.patch('ec2api.api.ec2utils.get_instance_uuid_from_int_id'))
        self.get_instance_uuid_from_int_id = (
            get_instance_uuid_from_int_id_patcher.start())
        self.addCleanup(get_instance_uuid_from_int_id_patcher.stop)
        # TODO(ft): patch EC2Client object instead of ec2client function
        # to make this similar to other patchers (neutron)
        # Now it's impossible since tests use EC2Client._parse_xml
        # Or patch neutron client function too, and make tests on client
        # functions
        ec2_patcher = mock.patch('ec2api.api.ec2client.ec2client')
        self.ec2 = ec2_patcher.start().return_value
        self.addCleanup(ec2_patcher.stop)
        isotime_patcher = mock.patch('ec2api.openstack.common.timeutils.'
                                     'isotime')
        self.isotime = isotime_patcher.start()
        self.addCleanup(isotime_patcher.stop)

    def execute(self, action, args):
        ec2_request = ec2api.api.apirequest.APIRequest(action, 'fake_v1', args)
        ec2_context = self._create_context()
        environ = {'REQUEST_METHOD': 'FAKE',
                   'ec2.request': ec2_request,
                   'ec2api.context': ec2_context}
        request = ec2api.wsgi.Request(environ)
        application = ec2api.api.Validator(ec2api.api.Executor())
        response = request.send(application)
        return self._check_and_transform_response(response, action)

    def _create_context(self):
        return ec2api.context.RequestContext(
            fakes.ID_OS_USER, fakes.ID_OS_PROJECT,
            'fake_access_key', 'fake_secret_key',
            service_catalog=[{'type': 'network',
                              'endpoints': [{'publicUrl': 'fake_url'}]}])

    def _check_and_transform_response(self, response, action):
        body = ec2client.EC2Client._parse_xml(response.body)
        if response.status_code == 200:
            action_tag = '%sResponse' % action
            self.assertIn(action_tag, body)
            body = body.pop(action_tag)
            self.assertIn('requestId', body)
            body.pop('requestId')
        else:
            self.assertIn('Response', body)
            body = body.pop('Response')
            self.assertIn('RequestID', body)
            body.pop('RequestID')
            self.assertEqual(1, len(body))
            self.assertIn('Errors', body)
            body = body.pop('Errors')
            self.assertEqual(1, len(body))
            self.assertIn('Error', body)
            self.assertEqual(2, len(body['Error']))
        body['status'] = response.status_code
        return body

    def assert_any_call(self, func, *args, **kwargs):
        calls = func.mock_calls
        for call in calls:
            call_args = call[1]
            if matchers.ListMatches(call_args, args, orderless_lists=True):
                return
        self.assertEqual(False, True)