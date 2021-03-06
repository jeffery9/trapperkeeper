# TrapperKeeper

## Description
TrapperKeeper is a suite of tools for ingesting and displaying SNMP traps. This
is designed as a replacement for snmptrapd and to supplement existing stateful
monitoring solutions.

Normally traps are stateless in nature which makes it difficult to monitor with
a system like nagios which requires polling a source. TrapperKeeper will store
traps in an active state for a configured amount of time before expiring. This
makes it possible to poll the service for active traps and alert off of those
traps.

One example might be a humidity alert. If you cross over the humidity threshold
and it clears immediately you might not want to be paged at 3am. But if it
continues to send a trap every 5 minutes while it's over that threshold the
combination of (host, oid, severity) will remain in an active state as
long as that trap's expiration duration is longer than 5 minutes. This allows
something like nagios to alarm when a single trap remains active for greater
than some period of time.

Another benefit is allowing aggregation of pages. Previously we'd just had an
e-mail to a pager per trap but now we're only paged based on the alert interval
regardless of how many traps we receive. This also allows us to schedule
downtime for a device during scheduled maintenance to avoid trap storms.

## Installation

New versions will be updated to PyPI pretty regularly so it should be as easy
as:

```bash
$ pip install trapperkeeper
```

Once you've created a configuration file with your database information you
can run the following to create the database schema.

```bash
$ python -m trapperkeeper.cmds.sync_db -c /path/to/trapperkeeper.yaml
```
## Tools

### trapperkeeper

The trapperkeeper command receives SNMP traps and handles e-mailing and writing
to the database. An example configuration file with documentation is available [here.](conf/trapperkeeper.yaml)

### trapdoor

trapdoor is a webserver that provides a view into the existing traps as well as an
API for viewing the state of traps. An example configuration file with documentation is available [here.](conf/trapdoor.yaml)

![Screenshot](https://raw.githubusercontent.com/dropbox/trapperkeeper/master/images/trapdoor.png)

#### API

##### /api/activetraps
_*Optional Parameters:*_
 * host
 * oid
 * severity

_*Returns:*_
```javascript
[
    (<host>, <oid>, <severity>)
]
```

##### /api/varbinds/<notification_id>

_*Returns:*_
```javascript
[
    {
        "notification_id": <notification_id>,
        "name": <varbind_name>,
        "pretty_value": <pretty_value>,
        "oid": <oid>,
        "value": <value>,
        "value_type": <value_type>
    }
]
```

## TODO

  * Allow Custom E-mail templates for TrapperKeeper
  * cdnjs prefix for local cdnjs mirrors
  * User ACLs for resolution
  * Logging resolving user

## Known Issues

  * Doesn't currently support SNMPv3
  * Doesn't currently support inform
  * Certain devices have been known to send negative TimeTicks. pyasn1 fails to handle this.
