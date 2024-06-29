# Satellite Finder for SAT>IP servers

This is a simple package that helps you align your satellite dish if you own a [SAT>IP][SatIpSpec] server. It allows you
to specify one or more frequencies to tune to (limited by the number of tuners available on the SAT>IP server). It will
then show you a UI with the signal strength and quality for each tuned frequency.

A satellite position often consists of multiple satellites, each with multiple transponders, and somtimes varying
beams and thus signal strengths. As this tools allows you to watch multiple frequencies at once, it can help you fine
tune your dish alignment.

However, beware that you already need to roughly align your dish before. This tool relies on your SAT>IP server being
able to get a lock on a frequency. If your dish is way off, you might not be able to get a lock on any frequency.


## Installation

I'm currently running this in a virtual environment. To set it up, run the following commands:

```shell
pip install pipenv
pipenv sync
pipenv shell
```


## Prerequisites

Make sure you open up the necessary UDP ports for RTP and RTCP in your firewall. For the first tuner, you'll need to
open up ports `57000/udp` and `57001/udp`. For the second tuner, you'll need to open up ports `57002/udp` and 
`57003/udp` and so forth.

Also, while aligning your dish, you should disable any other consumers of your SAT>IP server before running this script. 
Otherwise, you might not be able to utilize all tuners.


## Usage

You specify the URL to the SAT>IP server's XML specification, as well as one or more `-t`une options. Let's say your
SAT>IP server is available at `192.168.1.1`, your satellite dish is pointed to Astra 28.2E, and you want to tune to
BBC One HD and ITVBe concurrently. You would run the following command:

```shell
src/main.py -s http://192.168.1.1:38400/description.xml -t 10817.5,v,dvbs2,23000,34,BBC1HD -t 11097,v,dvbs2,23000,34,ITVBe
```

Let's dissect the options:
* `-s http://192.168.1.1:38400/description.xml`: This is the URL to your SAT>IP server's XML specification. The URL may
  vary depending on your server's make and model.
* `-t 10817.5,v,dvbs2,23000,34,BBC1HD`: This is the first channel you want to tune to. The format is
  `frequency,polarisation,modulation_system,symbol_rate,fec,channel_name`. The channel name is optional and is used to
  make it easier to identify the channel in the UI.
* `-t 11097,v,dvbs2,23000,34,ITVBe`: This is the second channel you want to tune to.

If your server has enough tuners available (don't forget to disable any other consumers of your server before) and it
can get a lock on these frequencies, it will start displaying a UI where it shows you the signal strength and quality
for each of the two channels.


[SatIpSpec]: https://web.archive.org/web/20240109234327/https://www.satip.info/sites/satip/files/resource/satip_specification_version_1_2_2.pdf