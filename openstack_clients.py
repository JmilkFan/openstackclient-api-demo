from openstackclient.identity.client import identity_client_v2
from keystoneclient import session as identity_session
import glanceclient
import novaclient.client as novaclient
import cinderclient.client as cinderclient


# FIXME(JmilkFan): Using oslo_config
NOVA_CLI_VER = 2
GLANCE_CLI_VER = 2
CINDER_CLI_VER = 2


class OpenstackClients(object):
    """Clients generator of openstack."""

    def __init__(self, auth_url, username, password, tenant_name):
        ### Identity authentication via keystone v2
        # An authentication plugin to authenticate the session with.
        auth = identity_client_v2.v2_auth.Password(
            auth_url=auth_url,
            username=username,
            password=password,
            tenant_name=tenant_name)

        try:
            self.session = identity_session.Session(auth=auth)
        except Exception as err:
            raise

        # Return a token as provided by the auth plugin.
        self.token = self.session.get_token()
        
    def get_glance_client(self, interface='public'):
        """Get the glance-client object."""
        # Get an endpoint as provided by the auth plugin.
        glance_endpoint = self.session.get_endpoint(service_type="image",
                                                    interface=interface)
        # Client for the OpenStack Images API.
        glance_client = glanceclient.Client(GLANCE_CLI_VER,
                                            endpoint=glance_endpoint,
                                            token=self.token)
        return glance_client

    def get_nova_client(self):
        """Get the nova-client object."""
        # Initialize client object based on given version. Don't need endpoint.
        nova_client = novaclient.Client(NOVA_CLI_VER, session=self.session)
        return nova_client

    def get_cinder_client(self, interface='public'):
        """Get the cinder-client object."""
        cinder_endpoint = self.session.get_endpoint(service_type='volume',
                                                    interface=interface)
        cinder_client = cinderclient.Client(CINDER_CLI_VER, session=self.session)
        return cinder_client
