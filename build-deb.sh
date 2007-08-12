#! /bin/sh

# Reset the tree to the checkout
cg-reset
cg-clean -d
#cg-restore -f ./tp/netlib/version.py

# Update to the latest version
cg-update

# Fix the version.py
cd tp/client
python version.py --fix > version-new.py
mv version-new.py version.py
cd ../..

# Update the debian changelog
cd debian; ./update-debian-changelog; cd ..

# Build the deb package
dpkg-buildpackage -us -uc -b -rfakeroot
