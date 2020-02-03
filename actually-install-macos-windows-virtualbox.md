Installing macOS on a VM in Windows is surprisingly complicated. Tutorials after tutorial after tutorial, guides that say that they’ve went through all of the tutorials and say that this one is a combination of all of them and it works, those that are outdated, those which were published last year, iBoot, Hackintosh, using a mac to download parts of the installer, none of which worked for me. Error after error after error, googling each error and then come up to more and more errors. I’ve finally found a solution.

First, I will assume that you do not have a mac, and cannot use a mac for any of the installation process. I will also assume that you want genuine Apple media downloaded from a legal source directly from Apple. This is how you do it:

1. Install VirtualBox and VirtualBox extensions on the Windows host (make sure to install the extensions and not the host twice; the headings are very similar.) Make sure that the extension version matches the VirtualBox version that you’ve installed. You may have to disable Hyper-V; if you do, restart twice after uninstalling. It has to be twice.

2. Install Cygwin (save the installation file; we will need it later), and then install apt-cyg via (https://stackoverflow.com/a/52546787/220935 in Cygwin; use this answer only, the other answers do not work.)

3. Re-run the Cygwin installer; when a blank list appears type “wget” in the search box, press enter (there is no search button), and select wget for installation then select the version to install. It doesn’t matter what version it is. Press next as many times as needed to install the software; it will take a few minutes.

4. Run apt-cyg install xxd coreutils gzip unzip inside of Cygwin. If you get a “command not found” error, make sure that the apt-cyg utility that was saved does not have the .txt extension when you saved it. Windows will sometimes automatically add it even if you delete the extension when saving the file.

5. Run curl -O https://raw.githubusercontent.com/myspaghetti/macos-guest-virtualbox/master/macos-guest-virtualbox.sh inside of Cygwin

6. Run chmod a+x ./macos-guest-virtualbox.sh inside of Cygwin
7. Run ./macos-guest-virtualbox.sh
8. Wait for everything to install. It will take many hours.

The virtual machine will appear in VirtualBox’s sidebar when you open it. I have tested these steps in a fresh new Windows VM and I have gotten to the step where it begins downloading the macOS images through the script, indicating that the preflight checks have passed.

**Note:** if you plan to take a snapshot, be careful. If you create a snapshot, use the VM, then delete the temporary files and try to revert back to the snapshot, it will fail because the snapshot relies on temporary files which no longer exist, and VirtualBox will not allow you to close the VM even if it's powered off and the icons are in strange places (it seems like a bug.) Before creating the snapshot, unlink all disks that do not end in VDI and all that begin with "Install". Save the VM and then you can delete the temporary files and take a snapshot.
