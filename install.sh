#!/bin/bash

target=~/apps/pybox
bin=~/apps/bin

cd $(dirname $0)
./build.sh
rm -rf $target/msaview{,_ui,_plugin_*}
cd $(dirname $0)/src
cp -r msaview{,_ui,_plugin_*} $target
cp msaview_ui/msaview $bin

