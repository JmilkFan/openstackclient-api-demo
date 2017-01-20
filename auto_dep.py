import sys
import os
from os import path
import time

import openstack_clients as os_cli

# FIXME(Fan Guiju): Using oslo_config and logging
AUTH_URL = 'http://200.21.18.3:35357/v2.0/'
USERNAME = 'admin'
PASSWORD = 'fanguiju'
PROJECT_NAME = 'admin'

DISK_FORMAT = 'qcow2'
IMAGE_NAME = 'ubuntu_server_1404_x64'
IMAGE_PATH = path.join(path.curdir, 'images', '.'.join([IMAGE_NAME, DISK_FORMAT]))

MIN_DISK_SIZE_GB = 20

KEYPAIR_NAME = 'jmilkfan-keypair'
KEYPAIT_PUB_PATH = '/home/stack/.ssh/id_rsa.pub'

DB_NAME = 'blog'
DB_USER = 'wordpress'
DB_PASS = 'fanguiju'
DB_BACKUP_SIZE = 5
DB_VOL_NAME = 'mysql-volume'
DB_INSTANCE_NAME = 'AUTO-DEP-DB'
MOUNT_POINT = '/dev/vdb'

BLOG_INSTANCE_NAME = 'AUTO-DEP-BLOG'

TIMEOUT = 60


class AutoDep(object):
    def __init__(self, auth_url, username, password, tenant_name):
        openstack_clients = os_cli.OpenstackClients(
            auth_url,
            username,
            password,
            tenant_name)
        self.glance = openstack_clients.get_glance_client()
        self.nova = openstack_clients.get_nova_client()
        self.cinder = openstack_clients.get_cinder_client()
    
    def _wait_for_done(self, objs, target_obj_name):
        """Wait for action done."""
        count = 0
        while count <= TIMEOUT:
            obj_list = objs.list()
            for obj in obj_list:
                if obj.name == target_obj_name:
                    break
            time.sleep(3)
            count += 3
        if count > TIMEOUT:
            raise

    def upload_image_to_glance(self):
        images = self.glance.images.list()
        for image in images:
           if image.name == IMAGE_NAME:
               return image
        new_image = self.glance.images.create(name=IMAGE_NAME,
                                              disk_format=DISK_FORMAT,
                                              container_format='bare',
                                              min_disk=MIN_DISK_SIZE_GB,
                                              visibility='public')
        # Open image file with read+binary.
        self.glance.images.upload(new_image.id, open(IMAGE_PATH, 'rb'))
        self._wait_for_done(objs=self.glance.images,
                            target_obj_name=IMAGE_NAME)
        image = self.glance.images.get(new_image.id)
        return image
    
    def create_volume(self):
        volumes = self.cinder.volumes.list()
        for volume in volumes:
            if volume.name == DB_VOL_NAME:
                return volume
        # cinderclient.v2.volumes:VolumeManager
        new_volume = self.cinder.volumes.create(
            size=DB_BACKUP_SIZE,
            name=DB_VOL_NAME,
            volume_type='lvmdriver-1',
            availability_zone='nova',
            description='backup volume of mysql server.')
        self._wait_for_done(objs=self.cinder.volumes,
                            target_obj_name=DB_VOL_NAME)
        return new_volume

    def get_flavor_id(self):
        flavors = self.nova.flavors.list()
        for flavor in flavors:
            if flavor.disk == MIN_DISK_SIZE_GB:
                return flavor.id
    
    def _get_ssh_pub_key(self):
        if not path.exists(KEYPAIT_PUB_PATH):
            raise
        return open(KEYPAIT_PUB_PATH, 'rb').read()
        
    def import_keypair_to_nova(self):
        keypairs = self.nova.keypairs.list()
        for keypair in keypairs:
            if keypair.name == KEYPAIR_NAME:
                return None
        keypair_pub = self._get_ssh_pub_key()
        self.nova.keypairs.create(KEYPAIR_NAME, public_key=keypair_pub)
        
    def nova_boot(self, image, volume):
        flavor_id = self.get_flavor_id()
        self.import_keypair_to_nova()
        db_instance = None

        servers = self.nova.servers.list()
        server_names = []
        for server in servers:
            server_names.append(server.name)
            #DB_INSTANCE_NAME
            if server.name == 'RHEL-65-MYSQL':
                db_instance = server

        if not db_instance:
            # Create the mysql server
            db_script_path = path.join(path.curdir, 'scripts/db_server.txt')
            db_script = open(db_script_path, 'r').read()
            db_script = db_script.format(DB_NAME, DB_USER, DB_PASS)
            db_instance = self.nova.servers.create(
                DB_INSTANCE_NAME,
                image.id,
                flavor_id,
                key_name=KEYPAIR_NAME,
                userdata=db_script)
            self._wait_for_done(objs=self.nova.servers,
                                target_obj_name=DB_INSTANCE_NAME)
        # Attach the mysql-vol into mysql server, device type is `vd`.
        # NOTE(Fan Guiju): What's mountpoint mean?
        self.cinder.volumes.attach(volume=volume,
                                   instance_uuid=db_instance.id,
                                   mountpoint=MOUNT_POINT)
        time.sleep(5)

        if BLOG_INSTANCE_NAME not in server_names:
            # Create the wordpress blog server
            # Nova-Network
            db_instance_ip = self.nova.servers.get(db_instance.id).networks['private'][0]
            blog_script_path = path.join(path.curdir, 'script.blog_server.txt')
            blog_script = open(blog_script_path, 'r').read()
            blog_script = blog_script.format(DB_NAME, DB_USER, DB_PASS, db_instance_ip)
            blog_instance = self.nova.servers.create(
                BLOG_INSTANCE_NAME,
                image.id,
                flavor_id,
                key_name=KEYPAIR_NAME,
                userdata=blog_script)
            self._wait_for_done(objs=self.nova.servers,
                                target_obj_name=BLOG_INSTANCE_NAME)

        servers = self.nova.servers.list(search_opts={'all_tenants':True})
        return servers

def main(argv):
    os.environ['LANG'] = 'en_US.UTF8'

    deploy = AutoDep(auth_url=AUTH_URL,
                     username=USERNAME,
                     password=PASSWORD,
                     tenant_name=PROJECT_NAME)
    import pdb
    pdb.set_trace()
    image = deploy.upload_image_to_glance()
    volume = deploy.create_volume()
    servers = deploy.nova_boot(image, volume)

if __name__ == '__main__':
    main(sys.argv)
