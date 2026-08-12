import json
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
            'NOTIFY_PACK_GIF': False,
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


@pytest.mark.unit
def test_discord_grouped_notification_format(monkeypatch):
    """Grouped notifications should build a Discord embed with the series name,
    a per-line issue list, and the cover issue number."""
    import mylar
    from mylar import notifiers

    monkeypatch.setattr(
        mylar, "CONFIG",
        FakeConfig(NOTIFY_GROUP_PACKS=True, DISCORD_ENABLED=True,
                   DISCORD_WEBHOOK_URL="http://example.com"),
    )

    posts = []

    class FakePost(object):
        def __init__(self, *a, **kw):
            self.status_code = 200
            self.text = 'ok'

    import requests
    monkeypatch.setattr(
        requests, 'post',
        lambda *a, **kw: (posts.append((a, kw)) or FakePost()),
    )

    discord = notifiers.DISCORD()
    attachment = (
        'Mylar has downloaded and post-processed 4 issue(s):\n'
        'Preacher Special: Saint of Killers (1996) #1\n'
        'Preacher Special: Saint of Killers (1996) #2\n'
        'Preacher Special: Saint of Killers (1996) #3\n'
        'Preacher Special: Saint of Killers (1996) #4'
    )
    discord.notify(
        'Download and Postprocessing completed',
        attachment,
        module='[POST-PROCESSING][NOTIFIER]',
        imageFile=None,
    )

    assert len(posts) == 1
    kwargs = posts[0][1]
    payload = json.loads(kwargs['data'])
    embed = payload['embeds'][0]
    assert embed['description'] == 'Issues downloaded!'
    fields = {f['name']: f['value'] for f in embed['fields']}
    assert list(fields.keys()) == ['Series']
    assert fields['Series'] == 'Preacher Special: Saint of Killers (1996)'
    assert payload['content'] == (
        'Mylar has downloaded and post-processed 4 issue(s): 1, 2, 3 and 4'
    )


@pytest.mark.unit
def test_build_slideshow_gif(monkeypatch):
    """Slideshow GIF builder should produce a GIF from multiple base64 covers,
    capped at max_frames, and return None when PIL is unavailable."""
    from mylar import getimage

    if getimage.PIL_Found is False:
        return

    # build two tiny JPEGs
    from PIL import Image
    import io as _io
    imgs = []
    for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255)):
        buf = _io.BytesIO()
        Image.new('RGB', (100, 150), color).save(buf, 'JPEG')
        imgs.append(__import__('base64').b64encode(buf.getvalue()).decode('ascii'))

    gif = getimage.build_slideshow_gif(imgs, width=400, max_frames=8)
    assert gif is not None
    assert gif[:6] == 'R0lGOD'  # GIF89a/GIF87a header

    # capped at max_frames
    many = imgs * 4
    gif2 = getimage.build_slideshow_gif(many, width=400, max_frames=8)
    assert gif2 is not None
    assert len(getimage.build_slideshow_gif(many, max_frames=2) or '') > 0

    # no valid frames -> None
    assert getimage.build_slideshow_gif([]) is None


@pytest.mark.unit
def test_notify_pack_gif_gated_by_discord(monkeypatch):
    """The slideshow GIF should only be produced when NOTIFY_PACK_GIF is on AND
    Discord is enabled; otherwise the static cover is used."""
    import mylar
    from mylar import PostProcessor, getimage

    monkeypatch.setattr(mylar, "CONFIG", FakeConfig(
        NOTIFY_GROUP_PACKS=True,
        NOTIFY_PACK_GIF=True,
        DISCORD_ENABLED=True,
    ))

    produced = []

    def fake_build(images, **kw):
        produced.append(images)
        return 'R0lGOD-fakegif'

    monkeypatch.setattr(getimage, 'build_slideshow_gif', fake_build)

    pp = object.__new__(PostProcessor.PostProcessor)
    pp.notify_buffer = []
    pp.notify_group_pack = True
    pp.module = '[TEST]'
    pp.notify_buffer = [
        {'prline': 'S (2000) #1', 'prline2': 'x', 'imageFile': 'AAA', 'module': '[T]'},
        {'prline': 'S (2000) #2', 'prline2': 'x', 'imageFile': 'BBB', 'module': '[T]'},
    ]

    sent = []
    pp.sendnotify = lambda *a, **kw: sent.append((a, kw))

    pp._flush_notify()
    assert len(produced) == 1
    assert produced[0] == ['AAA', 'BBB']
    # GIF passed to sendnotify
    assert sent[0][1]['imageFile'] == 'R0lGOD-fakegif'
