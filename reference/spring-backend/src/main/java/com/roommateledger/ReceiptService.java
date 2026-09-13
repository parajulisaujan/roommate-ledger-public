package com.roommateledger;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.*;
import java.security.*;
import java.time.LocalDate;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class ReceiptService {
  public boolean extractionAvailable() {
    return provider.available();
  }

  public record Item(
      String description,
      String rawDescription,
      BigDecimal quantity,
      Long unitPrice,
      @JsonProperty(required = true) long amount,
      String category,
      BigDecimal confidence,
      String scope,
      List<UUID> participants) {}

  public record Draft(
      String merchant,
      LocalDate date,
      String currency,
      UUID householdId,
      UUID payerId,
      List<Item> items,
      @JsonProperty(required = true) long subtotal,
      @JsonProperty(required = true) long discounts,
      @JsonProperty(required = true) long tax,
      @JsonProperty(required = true) long fees,
      @JsonProperty(required = true) long total) {}

  private final Store db;
  private final ExpenseService expenses;
  private final ObjectMapper mapper;
  private final ReceiptExtractionProvider provider;

  public ReceiptService(
      Store db, ExpenseService expenses, ObjectMapper mapper, ReceiptExtractionProvider provider) {
    this.db = db;
    this.expenses = expenses;
    this.mapper = mapper;
    this.provider = provider;
  }

  String encode(Draft d) {
    try {
      return mapper.writeValueAsString(d);
    } catch (Exception e) {
      throw ApiException.invalid("Invalid receipt.");
    }
  }

  Draft decode(Object d) {
    try {
      return mapper.readValue(d.toString(), Draft.class);
    } catch (Exception e) {
      throw ApiException.invalid("Invalid receipt data.");
    }
  }

  public Map<String, Object> get(UUID user, UUID id) {
    var r = db.one("SELECT * FROM receipt WHERE id=?", id);
    if (!user.equals(Store.uuid(r.get("owner_id")))) throw ApiException.forbidden();
    r.put("draft", decode(r.get("draft")));
    return r;
  }

  public Object list(UUID user) {
    return db.list(
        "SELECT id,status,error,created_at FROM receipt WHERE owner_id=? ORDER BY created_at DESC"
            + " LIMIT 50",
        user);
  }

  public UUID manual(UUID user) {
    return createDraft(user, "NEEDS_REVIEW");
  }

  private UUID createDraft(UUID user, String status) {
    UUID id = UUID.randomUUID();
    db.run(
        "INSERT INTO receipt(id,owner_id,status,draft) VALUES(?,?,?,?)",
        id,
        user,
        status,
        encode(new Draft("", LocalDate.now(), "USD", null, user, List.of(), 0, 0, 0, 0, 0)));
    return id;
  }

  public static String mime(byte[] b) {
    if (b.length >= 8
        && b[0] == (byte) 0x89
        && b[1] == 'P'
        && b[2] == 'N'
        && b[3] == 'G'
        && b[4] == 13
        && b[5] == 10
        && b[6] == 26
        && b[7] == 10) return "image/png";
    if (b.length >= 3 && b[0] == (byte) 0xff && b[1] == (byte) 0xd8 && b[2] == (byte) 0xff)
      return "image/jpeg";
    if (b.length >= 12
        && b[0] == 'R'
        && b[1] == 'I'
        && b[2] == 'F'
        && b[3] == 'F'
        && b[8] == 'W'
        && b[9] == 'E'
        && b[10] == 'B'
        && b[11] == 'P') return "image/webp";
    throw ApiException.invalid("Upload a real JPEG, PNG or WebP image.");
  }

  public Map<String, Object> upload(UUID user, MultipartFile file) {
    if (file.isEmpty() || file.getSize() > 8 * 1024 * 1024)
      throw ApiException.invalid("Upload an image between 1 byte and 8 MB.");
    byte[] bytes;
    try {
      bytes = file.getBytes();
    } catch (Exception e) {
      throw ApiException.invalid("Could not read image.");
    }
    if (bytes.length == 0 || bytes.length > 8 * 1024 * 1024)
      throw ApiException.invalid("Use a receipt image smaller than 8 MB.");
    String mime = ReceiptImage.validate(bytes);
    String declared = file.getContentType();
    if (declared != null && !declared.equals(mime) && !declared.equals("application/octet-stream"))
      throw ApiException.invalid("The declared content type does not match the image.");
    String hash;
    try {
      hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
    boolean duplicate =
        db.exists("SELECT id FROM receipt WHERE owner_id=? AND fingerprint=?", user, hash);
    UUID id = createDraft(user, "UPLOADED");
    db.run("UPDATE receipt SET fingerprint=?,status='PROCESSING' WHERE id=?", hash, id);
    try {
      Draft draft = provider.extract(bytes, mime);
      validateDraft(draft, false);
      db.run(
          "UPDATE receipt SET draft=?,status='NEEDS_REVIEW' WHERE id=? AND status='PROCESSING'",
          encode(draft),
          id);
    } catch (ApiException e) {
      db.run(
          "UPDATE receipt SET status='FAILED',error=? WHERE id=? AND status='PROCESSING'",
          e.getMessage(),
          id);
    } catch (RuntimeException e) {
      db.run(
          "UPDATE receipt SET status='FAILED',error=? WHERE id=? AND status='PROCESSING'",
          "Extraction failed. Retry the upload or enter receipt items manually.",
          id);
    }
    var result = get(user, id);
    result.put("duplicate", duplicate);
    return result;
  }

  public static void validateDraft(Draft d, boolean confirm) {
    if (d == null
        || d.items() == null
        || d.items().size() > 100
        || d.merchant() == null
        || d.merchant().length() > 120
        || d.date() == null
        || !"USD".equals(d.currency()))
      throw ApiException.invalid(
          "Receipt needs a valid merchant, date, USD currency and at most 100 items.");
    for (long v : new long[] {d.subtotal(), d.discounts(), d.tax(), d.fees(), d.total()})
      if (v < 0 || v > Money.MAX) throw ApiException.invalid("Invalid receipt totals.");
    for (Item i : d.items()) {
      if (i == null
          || i.description() == null
          || i.description().isBlank()
          || i.description().length() > 120
          || (i.rawDescription() != null && i.rawDescription().length() > 500)
          || i.category() == null
          || i.category().isBlank()
          || i.category().length() > 40
          || i.quantity() == null
          || i.quantity().signum() <= 0
          || i.quantity().compareTo(BigDecimal.valueOf(10000)) > 0
          || (i.unitPrice() != null && (i.unitPrice() < 0 || i.unitPrice() > Money.MAX))
          || (i.confidence() != null
              && (i.confidence().signum() < 0 || i.confidence().compareTo(BigDecimal.ONE) > 0)))
        throw ApiException.invalid(
            "Each item needs a description, category and positive quantity.");
      Money.positive(i.amount());
    }
    if (confirm) {
      if (d.items().isEmpty()) throw ApiException.invalid("Add at least one item.");
      long sum = d.items().stream().mapToLong(Item::amount).sum();
      if (sum != d.subtotal() || sum - d.discounts() + d.tax() + d.fees() != d.total())
        throw new ApiException(
            400,
            "INVALID_RECEIPT_TOTAL",
            "Items, discounts, tax and fees must reconcile exactly with the receipt total.");
      Money.positive(d.total());
    }
  }

  @Transactional
  public Object save(UUID user, UUID id, Draft draft) {
    db.one("SELECT id FROM receipt WHERE id=? FOR UPDATE", id);
    var receipt = get(user, id);
    if (!Set.of("NEEDS_REVIEW", "FAILED").contains(receipt.get("status")))
      throw new ApiException(
          409,
          "CONFLICT",
          "Only a reviewable or failed receipt can be edited. Processing receipts must finish"
              + " first.");
    validateDraft(draft, false);
    db.run(
        "UPDATE receipt SET draft=?,status='NEEDS_REVIEW',error=NULL WHERE id=?",
        encode(draft),
        id);
    return get(user, id);
  }

  /** Proportional adjustments use largest remainders, with receipt order breaking ties. */
  public static List<Long> adjusted(Draft d) {
    long subtotal = d.items().stream().mapToLong(Item::amount).sum();
    List<Long> amounts = new ArrayList<>();
    List<BigInteger> remainders = new ArrayList<>();
    long allocated = 0;
    for (var i : d.items()) {
      var qr =
          BigInteger.valueOf(d.total())
              .multiply(BigInteger.valueOf(i.amount()))
              .divideAndRemainder(BigInteger.valueOf(subtotal));
      long v = qr[0].longValueExact();
      amounts.add(v);
      remainders.add(qr[1]);
      allocated += v;
    }
    var order = new ArrayList<Integer>();
    for (int i = 0; i < amounts.size(); i++) order.add(i);
    order.sort(
        Comparator.<Integer, BigInteger>comparing(remainders::get)
            .reversed()
            .thenComparingInt(i -> i));
    for (int i = 0; i < d.total() - allocated; i++) {
      int index = order.get(i);
      amounts.set(index, amounts.get(index) + 1);
    }
    return amounts;
  }

  @Transactional
  public Object confirm(UUID user, UUID id) {
    db.one("SELECT id FROM receipt WHERE id=? FOR UPDATE", id);
    var receipt = get(user, id);
    if (!"NEEDS_REVIEW".equals(receipt.get("status")))
      throw new ApiException(
          409,
          "CONFLICT",
          "Save and review this receipt before confirmation. Confirmed receipts cannot be confirmed"
              + " again.");
    Draft d = (Draft) receipt.get("draft");
    validateDraft(d, true);
    var adjusted = adjusted(d);
    for (int index = 0; index < d.items().size(); index++) {
      Item i = d.items().get(index);
      boolean personal = "PERSONAL".equals(i.scope());
      if (adjusted.get(index) == 0)
        throw ApiException.invalid(
            "Adjustments reduce an item to zero. Combine or remove zero-value items before"
                + " confirming.");
      if (personal && d.payerId() != null && !d.payerId().equals(user))
        throw ApiException.invalid(
            "For items paid by another roommate, choose selected members instead of private"
                + " personal scope.");
      expenses.create(
          user,
          new ExpenseService.Input(
              i.description(),
              d.merchant(),
              adjusted.get(index),
              i.category(),
              i.scope(),
              personal ? null : d.householdId(),
              personal ? user : d.payerId(),
              d.date(),
              "EQUAL",
              i.participants(),
              null,
              "Receipt item; tax, fees and discounts allocated proportionally.",
              null),
          id,
          null);
    }
    db.run("UPDATE receipt SET status='CONFIRMED' WHERE id=?", id);
    // Keep the complete receipt audit private: mixed receipts can contain personal items.
    db.audit(user, null, "RECEIPT_CONFIRMED", id);
    return get(user, id);
  }
}
