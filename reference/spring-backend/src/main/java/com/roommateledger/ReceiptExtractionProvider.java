package com.roommateledger;

public interface ReceiptExtractionProvider {
  boolean available();

  ReceiptService.Draft extract(byte[] image, String mime);
}
