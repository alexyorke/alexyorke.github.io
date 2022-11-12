---
title: "Actually install macOS in Virtual Box on Windows"
date: 2020-02-02
---

Installing macOS on a VM in Windows is surprisingly complicated. Tutorials after tutorial after tutorial, guides that say that they’ve went through all of the tutorials and say that this one is a combination of all of them and it works, those that are outdated, those which were published last year, iBoot, Hackintosh, using a mac to download parts of the installer, none of which worked for me. Error after error after error, googling each error and then come up to more and more errors. I’ve finally found a solution.

First, I will assume that you do not have a mac, and cannot use a mac for any of the installation process. I will also assume that you want genuine Apple media downloaded from a legal source directly from Apple. This is how you do it:

1. Install VirtualBox and VirtualBox extensions on the Windows host (make sure to install the extensions and not the host twice; the headings are very similar.) Make sure that the extension version matches the VirtualBox version that you’ve installed. You may have to disable Hyper-V; if you do, restart twice after uninstalling. It has to be twice.

2. Install Cygwin (save the installation file; we will need it later), and then install `apt-cyg` via (https://stackoverflow.com/a/52546787/220935 in Cygwin; use this answer only, the other answers do not work.)

3. Re-run the Cygwin installer; when a blank list appears type `wget` in the search box, press enter (there is no search button), and select wget for installation then select the version to install. It doesn’t matter what version it is. Press next as many times as needed to install the software; it will take a few minutes.

4. Run `apt-cyg install xxd coreutils gzip unzip` inside of Cygwin. If you get a “command not found” error, make sure that the apt-cyg utility that was saved does not have the .txt extension when you saved it. Windows will sometimes automatically add it even if you delete the extension when saving the file.

5. Run `curl -O https://raw.githubusercontent.com/myspaghetti/macos-guest-virtualbox/master/macos-guest-virtualbox.sh` inside of Cygwin

6. Run `chmod a+x ./macos-guest-virtualbox.sh` inside of Cygwin
7. Run `./macos-guest-virtualbox.sh`
8. Wait for everything to install. It will take many hours; the script will ask you to press enter at certain times.

The virtual machine will appear in VirtualBox’s sidebar when you open it. I have tested these steps in a fresh new Windows VM and I have gotten to the step where it begins downloading the macOS images through the script, indicating that the preflight checks have passed.

**Note:** if you plan to take a snapshot or want to **export to OVF**, be careful. If you create a snapshot, use the VM, then delete the temporary files and try to revert back to the snapshot, it will fail because the snapshot relies on temporary files which no longer exist, and VirtualBox will not allow you to close the VM even if it's powered off and the icons are in strange places (it seems like a bug.) Before creating the snapshot, unlink these disks: `Mojave_Installation_Files.vdi` and `Install Mojave.vdi`. Save the VM and then you can delete the temporary files and take a snapshot.

## Ut oh, I deleted temporary files after creating a snapshot

Summary: create a fake VDI where VirtualBox wants it, and then set the UUID to the old one so that VirtualBox "thinks" it is still there.

Here's how to fix it:

- close all VirtualBox processes (go into Task Manager and close them; anything with the VirtualBox icon suffices.) There is usually a "VirtualBox Manager" that has to be closed too. It's possible that VirtualBox is stuck or hung, in which case you will have to force quit it.

- create a file at `C:/cygwin64/home/username/Install Mojave.vdi` using a blank VDI file. You can make one by "adding" a disk to the VM, but then just don't attach it when you get to the end. Rename the file to `Install Mojave.vdi` and then move to that path. Or, you can download the one I made here: https://github.com/alexyorke/alexyorke.github.io/blob/master/blank_vdi.zip (unzip first.)

- restore snapshot and copy the second UUID to your clipboard from Details error message (click on details to see UUID). If you don't want to restore the snapshot, the UUID is in the `C:\Users\username\.VirtualBox\virtualbox.xml` file; find the disk that starts with "Install".

- set UUID via `VBoxManage internalcommands sethduuid "C:\cygwin64\home\username\Install Mojave.vdi" <paste in UUID>` in `cmd`

- try to restore snapshot again. It should work; you will get a non-fatal error message. Click OK and the VM will continue booting. To stop seeing this message, remove the disk with the (!) next to it (`Mojave_Installation_Files`) in the VMs settings (it won't complain when you try to remove it.)

- the file at `C:/cygwin64/home/username/Install Mojave.vdi` can now be deleted.

If it doesn't boot, make sure that the UUID was correct, and that the character `}` or `{` was not copied.
