package com.roommateledger;

import java.io.ByteArrayInputStream;
import javax.imageio.ImageIO;
import javax.imageio.stream.MemoryCacheImageInputStream;

/** Decode supported images in bounded memory; never create public or temporary image files. */
final class ReceiptImage {
  private ReceiptImage() {}

  static String validate(byte[] bytes) {
    String mime = ReceiptService.mime(bytes);
    try (var input = new MemoryCacheImageInputStream(new ByteArrayInputStream(bytes))) {
      var readers = ImageIO.getImageReaders(input);
      if (!readers.hasNext()) throw ApiException.invalid("The image is corrupt or unsupported.");
      var reader = readers.next();
      try {
        reader.setInput(input, true, true);
        int width = reader.getWidth(0), height = reader.getHeight(0);
        if (width <= 0
            || height <= 0
            || width > 12000
            || height > 12000
            || (long) width * height > 24_000_000)
          throw ApiException.invalid(
              "Receipt images must be at most 24 megapixels and 12,000 pixels per side.");
        var decoded = reader.read(0);
        if (decoded == null) throw ApiException.invalid("The image could not be decoded.");
        decoded.flush();
      } finally {
        reader.dispose();
      }
      return mime;
    } catch (ApiException e) {
      throw e;
    } catch (Exception e) {
      throw ApiException.invalid(
          "The image is corrupt or unsupported. Choose another JPEG, PNG or WebP photo.");
    }
  }
}
