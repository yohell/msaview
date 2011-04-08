#!/bin/bash

target=~/apps/pybox
rm -rf $target/msaview{,_ui,_plugin_*}
cd $(dirname $0)/src
cp -r msaview{,_ui,_plugin_*} $target

