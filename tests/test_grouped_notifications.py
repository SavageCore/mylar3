import pytest


class FakeConfig(object):
    def __init__(self, **overrides):
        defaults = {
            'PROWL_ENABLED': False,
            'PUSHOVER_ENABLED': False,
            'PUSHOVER_IMAGE': False,
            'BOXCAR_ENABLED': False,
            'PUSHBULLET_ENABLED': False,
            'TELEGRAM_ENABLED': False,
            'TELEGRAM_IMAGE': False,
            'SLACK_ENABLED': False,
            'MATTERMOST_ENABLED': False,
            'MATTERMOST_WEBHOOK_URL': None,
            'DISCORD_ENABLED': False,
            'DISCORD_WEBHOOK_URL': None,
            'EMAIL_ENABLED': False,
            'EMAIL_ONPOST': False,
            'GOTIFY_ENABLED': False,
            'NOTIFY_GROUP_PACKS': False,
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(self, k, v)


@pytest.mark.unit
def test_buffer_and_flush_grouped_notifications(monkeypatch):
    """Per-issue notifications from a pack should be buffered and flushed as a
    single grouped notification when NOTIFY_GROUP_PACKS is enabled."""
    import mylar
    from mylar import PostProcessor, notifiers

    monkeypatch.setattr(
        mylar, "CONFIG",
        FakeConfig(NOTIFY_GROUP_PACKS=True, DISCORD_ENABLED=True,
                   DISCORD_WEBHOOK_URL="http://example.com",
                   MATTERMOST_ENABLED=True),
    )

    sent = []
    mm_sent = []

    class FakeDiscord(object):
        def __init__(self):
            pass

        def notify(self, text, attachment_text, **kwargs):
            sent.append(attachment_text)

    class FakeMattermost(object):
        def __init__(self):
            pass

        def notify(self, text, attachment_text, **kwargs):
            mm_sent.append((attachment_text, kwargs.get('metadata')))

    monkeypatch.setattr(notifiers, "DISCORD", FakeDiscord)
    monkeypatch.setattr(notifiers, "MATTERMOST", FakeMattermost)

    pp = object.__new__(PostProcessor.PostProcessor)
    pp.issuearcid = None
    pp.notify_buffer = []
    pp.notify_group_pack = True
    pp.module = '[FOLDER-CHECK][POST-PROCESSING]'

    # three issues processed from a pack
    for num in (1, 2, 12):
        pp.sendnotify(
            'Watchmen', '1986', '#%s' % num, 'no',
            '[FOLDER-CHECK][POST-PROCESSING]', None,
        )
    assert len(sent) == 0, 'per-issue notifications should be buffered'
    assert len(mm_sent) == 0, 'per-issue notifications should be buffered'

    pp._flush_notify()
    assert len(sent) == 1, 'one grouped notification should be sent'
    assert '#1' in sent[0]
    assert '#2' in sent[0]
    assert '#12' in sent[0]
    assert len(mm_sent) == 1, 'one grouped mattermost notification'
    mm_text, mm_meta = mm_sent[0]
    assert '#1' in mm_text
    assert mm_meta['issue'] == '3 issues'


@pytest.mark.unit
def test_no_grouping_when_disabled(monkeypatch):
    """With NOTIFY_GROUP_PACKS disabled, notifications send immediately."""
    import mylar
    from mylar import PostProcessor, notifiers

    monkeypatch.setattr(
        mylar, "CONFIG",
        FakeConfig(NOTIFY_GROUP_PACKS=False, DISCORD_ENABLED=True,
                   DISCORD_WEBHOOK_URL="http://example.com"),
    )

    sent = []

    class FakeDiscord(object):
        def __init__(self):
            pass

        def notify(self, text, attachment_text, **kwargs):
            sent.append(attachment_text)

    monkeypatch.setattr(notifiers, "DISCORD", FakeDiscord)

    pp = object.__new__(PostProcessor.PostProcessor)
    pp.issuearcid = None
    pp.notify_buffer = []
    pp.notify_group_pack = False
    pp.module = '[POST-PROCESSING]'

    pp.sendnotify('Watchmen', '1986', '#1', 'no', '[POST-PROCESSING]', None)
    assert len(sent) == 1
    assert '#1' in sent[0]
