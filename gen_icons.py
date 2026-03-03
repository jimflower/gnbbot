"""Generate valid Teams app icons and repackage the zip."""
import struct, zlib, os, zipfile

def make_png(width, height, r, g, b, a=255):
    """Create a valid RGBA PNG file."""
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)

    raw = b''
    for _ in range(height):
        raw += b'\x00' + bytes([r, g, b, a] * width)

    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))  # color type 6 = RGBA
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b'')
    )

os.makedirs('teams-app', exist_ok=True)

# Color icon: 192x192, GNB blue
with open('teams-app/color.png', 'wb') as f:
    f.write(make_png(192, 192, 0, 66, 130))

# Outline icon: 32x32, white on transparent
with open('teams-app/outline.png', 'wb') as f:
    f.write(make_png(32, 32, 255, 255, 255, 0))  # fully transparent

# Repackage zip
with zipfile.ZipFile('gnbbot-teams.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    z.write('teams-app/manifest.json', 'manifest.json')
    z.write('teams-app/color.png',     'color.png')
    z.write('teams-app/outline.png',   'outline.png')

print("Done — gnbbot-teams.zip regenerated")
