#
# Regular cron jobs for the msaview package
#
0 4	* * *	root	[ -x /usr/bin/msaview_maintenance ] && /usr/bin/msaview_maintenance
