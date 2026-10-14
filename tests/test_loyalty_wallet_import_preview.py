"""Real codec+HTTP preview, synthetic card numbers only, never user photos."""
import base64
import pytest
from tests.test_loyalty_wallet_http import http_wallet
from loyalty_wallet import render_code, decode_image


@pytest.mark.parametrize('fmt,code', [('EAN_13', '0042100005264'), ('CODE_128', '00012345'), ('QR_CODE', 'SYNTHETIC-LOYALTY-0001')])
def test_decode_returns_verified_inline_preview_without_saving(http_wallet, fmt, code):
    client, _, db = http_wallet
    photo = base64.b64decode(render_code(fmt, code).split(',', 1)[1])
    response = client.post('/api/wallet/decode', content=photo, headers={
        'Authorization': 'Bearer synthetic-alice', 'Content-Type': 'image/png',
    })
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.json()['saved'] is False
    candidates = response.json()['candidates']
    chosen = next(c for c in candidates if c['format'] == fmt and c['code'] == code)
    assert chosen['image'].startswith('data:image/png;base64,')
    assert {'format': fmt, 'code': code} in decode_image(base64.b64decode(chosen['image'].split(',', 1)[1]))
    assert db.loyalty_wallets.docs == {}


def test_equivalent_ean_upc_candidates_have_readable_previews(http_wallet):
    client, _, _ = http_wallet
    photo = base64.b64decode(render_code('EAN_13', '0042100005264').split(',', 1)[1])
    result = client.post('/api/wallet/decode', content=photo, headers={
        'Authorization': 'Bearer synthetic-alice', 'Content-Type': 'image/png',
    }).json()
    assert {c['format'] for c in result['candidates']} == {'EAN_13', 'UPC_A'}
    for candidate in result['candidates']:
        assert candidate['image'].startswith('data:image/png;base64,')
