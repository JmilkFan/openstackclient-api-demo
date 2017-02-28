#!/usr/bin/env python
#encoding=utf8


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
IMAGE_PATH = path.join(path.curdir, 'images',
                       '.'.join([IMAGE_NAME, DISK_FORMAT]))

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
        # FIXME(Fan Guiju): Using self._glance & self._nova & self._cinder
        self._glance = openstack_clients.get_glance_client()
        self._nova = openstack_clients.get_nova_client()
        self._cinder = openstack_clients.get_cinder_client()

    def _wait_for_done(self, objs, target_obj_name):
        """Wait for action done."""
        count = 0
        while count <= TIMEOUT:
            for obj in objs.list():
                if obj.name == target_obj_name:
                    return
            time.sleep(3)
            count += 3
        raise

    def upload_image_to_glance(self):
        images = self._glance.images.list()
        for image in images:
            if image.name == IMAGE_NAME:
                return image
        new_image = self._glance.images.create(name=IMAGE_NAME,
                                               disk_format=DISK_FORMAT,
                                               container_format='bare',
                                               min_disk=MIN_DISK_SIZE_GB,
                                               visibility='public')
        # Open image file with read+binary.
        self._glance.images.upload(new_image.id, open(IMAGE_PATH, 'rb'))
        self._wait_for_done(objs=self._glance.images,
                            target_obj_name=IMAGE_NAME)
        image = self._glance.images.get(new_image.id)
        return image

    def create_volume(self):
        volumes = self._cinder.volumes.list()
        for volume in volumes:
            if volume.name == DB_VOL_NAME:
                return volume
        # cinderclient.v2.volumes:VolumeManager
        new_volume = self._cinder.volumes.create(
            size=DB_BACKUP_SIZE,
            name=DB_VOL_NAME,
            volume_type='lvmdriver-1',
            availability_zone='nova',
            description='backup volume of mysql server.')
        if new_volume:
            return new_volume
        else:
            raise

    def get_flavor_id(self):
        flavors = self._nova.flavors.list()
        for flavor in flavors:
            if flavor.disk == MIN_DISK_SIZE_GB:
                return flavor.id

    def _get_ssh_pub_key(self):
        if not path.exists(KEYPAIT_PUB_PATH):
            raise
        return open(KEYPAIT_PUB_PATH, 'rb').read()

    def import_keypair_to_nova(self):
        keypairs = self._nova.keypairs.list()
        for keypair in keypairs:
            if keypair.name == KEYPAIR_NAME:
                return None
        keypair_pub = self._get_ssh_pub_key()
        self._nova.keypairs.create(KEYPAIR_NAME, public_key=keypair_pub)

    def nova_boot(self, image, volume):
        flavor_id = self.get_flavor_id()
        self.import_keypair_to_nova()
        db_instance = False

        servers = self._nova.servers.list()
        server_names = []
        for server in servers:
            server_names.append(server.name)
            if server.name == DB_INSTANCE_NAME:
                db_instance = server

        if not db_instance:
            # Create the mysql server
            db_script_path = path.join(path.curdir, 'scripts/db_server.txt')
            db_script = open(db_script_path, 'r').read()
            db_script = db_script.format(DB_NAME, DB_USER, DB_PASS)
            # FIXME(Fan Guiju): Using instance_uuid to check the action whether done.
            db_instance = self._nova.servers.create(
                # FIXME(Fan Guiju): Using the params `block_device_mapping` to attach the volume.
                DB_INSTANCE_NAME,
                image.id,
                flavor_id,
                key_name=KEYPAIR_NAME,
                userdata=db_script)
            if not self._nova.server.get(db_instance.id):
                self._wait_for_done(objs=self._nova.servers,
                                    target_obj_name=DB_INSTANCE_NAME)
        # Attach the mysql-vol to mysql server, device type is `vd`.
        self._cinder.volumes.attach(volume=volume,
                                    instance_uuid=db_instance.id,
                                    mountpoint=MOUNT_POINT)
        time.sleep(5)

        if BLOG_INSTANCE_NAME not in server_names:
            # Create the wordpress blog server
            # Nova-Network
            db_instance_ip = self._nova.servers.\
                get(db_instance.id).networks['private'][0]
            blog_script_path = path.join(path.curdir, 'scripts/blog_server.txt')
            blog_script = open(blog_script_path, 'r').read()
            blog_script = blog_script.format(DB_NAME,
                                             DB_USER,
                                             DB_PASS,
                                             db_instance_ip)
            self._nova.servers.create(BLOG_INSTANCE_NAME,
                                      image.id,
                                      flavor_id,
                                      key_name=KEYPAIR_NAME,
                                      userdata=blog_script)
            self._wait_for_done(objs=self._nova.servers,
                                target_obj_name=BLOG_INSTANCE_NAME)

        servers = self._nova.servers.list(search_opts={'all_tenants': True})
        return servers


def main():
    """FIXME(Fan Guiju): Operation manual."""
    os.environ['LANG'] = 'en_US.UTF8'

    deploy = AutoDep(auth_url=AUTH_URL,
                     username=USERNAME,
                     password=PASSWORD,
                     tenant_name=PROJECT_NAME)
    image = deploy.upload_image_to_glance()
    volume = deploy.create_volume()
    deploy.nova_boot(image, volume)

if __name__ == '__main__':
    main()
