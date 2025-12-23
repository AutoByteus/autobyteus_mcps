from PIL import Image, ImageDraw

def create_test_image(path, color, size=(100, 100)):
    img = Image.new('RGB', size, color=color)
    d = ImageDraw.Draw(img)
    d.text((10, 40), "Test Image", fill=(255, 255, 255))
    img.save(path)

if __name__ == "__main__":
    create_test_image("pptx-mcp/tests/test_red.png", 'red')
    create_test_image("pptx-mcp/tests/test_blue.png", 'blue')
