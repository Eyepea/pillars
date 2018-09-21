import mock
import uuid
import pytest
import pillars
import asyncio
import aiohttp
import asynctest


@pytest.fixture
def app():
    return pillars.Application(name='pytest-fixture')


@pytest.fixture(params=(pytest.param({}, id='ari:empty'), ))
def ari_client(request, app):

    auth = aiohttp.BasicAuth(login='rabbit', password='hunter2')
    client = pillars.engines.ari.AriClient(app=app, auth=auth, url='http://localhost:80')

    if isinstance(request.param, Exception):
        client._request = asynctest.CoroutineMock(side_effect=request.param)
    else:
        client._request = asynctest.CoroutineMock(return_value=request.param)

    return client


class TestAri:

    @pytest.mark.asyncio
    async def test_ari_client(self, ari_client, app):
        assert ari_client._startup in app.on_startup
        assert ari_client._shutdown in app.on_shutdown

        await app.start()
        assert isinstance(ari_client._client, aiohttp.client.ClientSession)

        await app.stop()
        assert ari_client._client.closed

    @mock.patch("time.time", mock.MagicMock(return_value=1534688291.051845))
    def test_channel_counter(self):
        counter = pillars.engines.ari.ChannelCounter()
        assert counter.new() == "1534688291.1"
        assert counter.new() == "1534688291.2"

    @mock.patch("time.time", mock.MagicMock(return_value=1534688291.051845))
    def test_channel_counter_reset(self):
        counter = pillars.engines.ari.ChannelCounter()
        assert counter.new() == "1534688291.1"
        assert counter.new() == "1534688291.2"

        with mock.patch('time.time', mock.MagicMock(return_value=1537533343.051845)):
            assert counter.new() == "1537533343.1"
            assert counter.new() == "1537533343.2"

    @mock.patch("time.time", mock.MagicMock(return_value=1534688291.051845))
    def test_generate_channel_id(self, ari_client):
        channel = ari_client.generate_channel_id()
        assert channel == "1534688291.1"

    @mock.patch("time.time", mock.MagicMock(return_value=1534688291.051845))
    def test_generate_channel_id_prefix(self, ari_client):
        channel_one = ari_client.generate_channel_id(channel_prefix="hello")
        assert channel_one == "hello.1534688291.1"

        channel_two = ari_client.generate_channel_id(channel_prefix="world")
        assert channel_two == "world.1534688291.2"

        channel_three = ari_client.generate_channel_id(channel_prefix="hello")
        assert channel_three == "hello.1534688291.3"

    @pytest.mark.asyncio
    async def test_request(self, ari_client):
        response = await ari_client.request(
            method='GET',
            url='ping'
        )
        assert response == {}

    @pytest.mark.asyncio
    async def test_status(self, ari_client):
        status = await ari_client.status()
        assert status is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize('ari_client', (
            pytest.param(aiohttp.client_exceptions.ClientConnectionError(), id='ari:ClientConnectionError'),
            pytest.param(aiohttp.ClientResponseError(status=400, history=None, request_info=None), id='ari:ClientResponseError')
    ), indirect=True)
    async def test_failed_status(self, ari_client):
        status = await ari_client.status()
        assert status is False


class TestPG:

    @pytest.mark.parametrize("input,output", [
        pytest.param("hello world", b'''\x01"hello world"''', id='pg-jsonb-encoder:text'),
        pytest.param({"Hello": "world"}, b'''\x01{"Hello":"world"}''', id='pg-jsonb-encoder:dict'),
        pytest.param({"foo": ["bar", "baz"]}, b'''\x01{"foo":["bar","baz"]}''', id='pg-jsonb-encoder:dict-list')
    ])
    def test_jsonb_encoder(self, input, output):
        result = pillars.engines.pg.jsonb_encoder(input)
        assert result == output

    @pytest.mark.parametrize("input,exception", [
        pytest.param({"foo": {"bar": uuid.uuid4()}}, (UnicodeDecodeError, OverflowError), id='pg-jsonb-encoder-exception:uuid'),
    ])
    def test_jsonb_encoder_error(self, input, exception):
        with pytest.raises(exception):
            pillars.engines.pg.jsonb_encoder(input)

    @pytest.mark.parametrize("output,input", [
        pytest.param("hello world", b'''\x01"hello world"''', id='pg-jsonb-decoder:text'),
        pytest.param({"Hello": "world"}, b'''\x01{"Hello":"world"}''', id='pg-jsonb-decoder:dict'),
        pytest.param({"foo": ["bar", "baz"]}, b'''\x01{"foo":["bar","baz"]}''', id='pg-jsonb-decoder:dict-list')
    ])
    def test_jsonb_decoder(self, input, output):
        result = pillars.engines.pg.jsonb_decoder(input)
        assert result == output
