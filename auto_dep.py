import sys
import os
from os import path
import time

import openstack_clients as os_cli

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
        time.sleep(5)
        image = self.glance.images.get(new_image.id)
        return image
    
    def create_volume(self):
        # /usr/local/lib/python2.7/dist-packages/cinderclient/v2/volumes.py
        new_volume = self.cinder.volumes.create(
            size=DB_BACKUP_SIZE,
            name='mysql-vol',
            volume_type='lvmdriver-1',
            availability_zone='nova',
            description='backup volume of mysql server.')
        time.sleep(10)
        volume = self.cinder.volumes.get(new_volume.id)
        return volume

    def get_flavor_id(self):
        flavors = self.nova.flavors.list()
        for flavor in flavors:
            if flavor.disk == MIN_DISK_SIZE_GB:
                return flavor.id
    
    def get_ssh_pub_key(self):
        if not path.exists(KEYPAIT_PUB_PATH):
            raise
        return open(KEYPAIT_PUB_PATH, 'rb').read()
        
    def import_keypair_to_nova(self):
        keypairs = self.nova.keypairs.list()
        keypair_names = []
        for keypair in keypairs:
            keypair_names.append(keypair.name)
        if KEYPAIR_NAME not in keypair_names:
            keypair_pub = get_ssh_pub_key()
            self.nova.keypairs.create(KEYPAIR_NAME, public_key=keypair_pub)
        
    def nova_boot(self, image):
        flavor_id = self.get_flavor_id()
        self.import_keypair_to_nova()

        db_script_path = path.join(path.curdir, 'scripts/db_server.txt')
        db_script = open(db_script_path, 'r').read()
        db_script = db_script.format(DB_NAME, DB_NAME, DB_USER, DB_PASS)
        db_instance = self.nova.servers.create(
            'RHEL-65-MYSQL',
            image.id,
            flavor_id,
            key_name=KEYPAIR_NAME,
            userdata=db_script)
        time.sleep(10)

        # Nova-Network
        db_instance_ip = self.nova.servers.get(db_instance.id).networks['private'][0]
        blog_script_path = path.join(path.curdir, 'script.blog_server.txt')
        blog_script = open(blog_script_path, 'r').read()
        blog_script = blog_script.format(DB_NAME, DB_USER, DB_PASS, db_instance_ip)
        blog_instance = self.nova.servers.create(
            'RHEL-65-WORDPRESS',
            image.id,
            flavor_id,
            key_name=KEYPAIR_NAME,
            userdata=blog_script)
        time.sleep(20)

        servers = self.nova.servers.list(search_opts={'all_tenants':True})

def main(argv):
    os.environ['LANG'] = 'en_US.UTF8'

    deploy = AutoDep(auth_url=AUTH_URL,
                     username=USERNAME,
                     password=PASSWORD,
                     tenant_name=PROJECT_NAME)
    import pdb
    pdb.set_trace()
    deploy.create_volume()
    image = deploy.upload_image_to_glance()
    deploy.nova_boot(image)

if __name__ == '__main__':
    main(sys.argv)
