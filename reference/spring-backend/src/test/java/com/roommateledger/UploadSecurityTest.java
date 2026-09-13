package com.roommateledger;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class UploadSecurityTest {
  @Autowired ReceiptService receipts;
  @Autowired Store db;
  @MockitoBean ReceiptExtractionProvider provider;
  UUID user;

  @BeforeEach
  void account() {
    user = UUID.randomUUID();
    db.run(
        "INSERT INTO app_user(id,name,email,password_hash) VALUES(?,?,?,?)",
        user,
        "Fictional upload test",
        user + "@example.test",
        "unused");
  }

  static byte[] fixture(String type) throws Exception {
    try (var stream = UploadSecurityTest.class.getResourceAsStream("/fixtures/pixel." + type)) {
      return stream.readAllBytes();
    }
  }

  ReceiptService.Draft draft() {
    return new ReceiptService.Draft(
        "Fictional shop",
        LocalDate.now(),
        "USD",
        null,
        user,
        List.of(
            new ReceiptService.Item(
                "Rice",
                "Rice",
                BigDecimal.ONE,
                100L,
                100,
                "Groceries",
                null,
                "PERSONAL",
                List.of(user))),
        100,
        0,
        0,
        0,
        100);
  }

  @ParameterizedTest
  @ValueSource(strings = {"png", "jpeg", "webp"})
  void actualSupportedImagesUseGeneratedIdsAndRemainPrivate(String type) throws Exception {
    when(provider.extract(any(), eq("image/" + type))).thenReturn(draft());
    var receipt =
        receipts.upload(
            user,
            new MockMultipartFile(
                "file", "../../not-an-image.exe", "image/" + type, fixture(type)));
    UUID id = Store.uuid(receipt.get("id"));
    assertThat(id).isNotNull();
    assertThat(receipt.get("status")).isEqualTo("NEEDS_REVIEW");
    assertThat(db.list("SELECT id FROM expense WHERE receipt_id=?", id)).isEmpty();
    assertThatThrownBy(() -> receipts.get(UUID.randomUUID(), id)).isInstanceOf(ApiException.class);
    receipts.save(user, id, draft());
    receipts.confirm(user, id);
    assertThat(db.list("SELECT amount FROM expense WHERE receipt_id=?", id)).hasSize(1);
  }

  @ParameterizedTest
  @ValueSource(strings = {"png", "jpeg", "webp"})
  void truncatedFilesAreRejectedBeforeProvider(String type) throws Exception {
    assertThatThrownBy(
            () ->
                receipts.upload(
                    user,
                    new MockMultipartFile(
                        "file",
                        "receipt." + type,
                        "image/" + type,
                        Arrays.copyOf(fixture(type), 12))))
        .isInstanceOf(ApiException.class);
    verifyNoInteractions(provider);
  }

  @Test
  void sizeEmptySpoofedMimeAndUnsupportedFormatsAreRejected() throws Exception {
    assertThatThrownBy(
            () ->
                receipts.upload(user, new MockMultipartFile("file", new byte[8 * 1024 * 1024 + 1])))
        .isInstanceOf(ApiException.class);
    assertThatThrownBy(() -> receipts.upload(user, new MockMultipartFile("file", new byte[0])))
        .isInstanceOf(ApiException.class);
    assertThatThrownBy(
            () ->
                receipts.upload(
                    user,
                    new MockMultipartFile("file", "receipt.jpg", "image/jpeg", fixture("png"))))
        .isInstanceOf(ApiException.class);
    assertThatThrownBy(
            () ->
                receipts.upload(
                    user,
                    new MockMultipartFile(
                        "file", "receipt.png", "image/png", "<script>bad</script>".getBytes())))
        .isInstanceOf(ApiException.class);
    verifyNoInteractions(provider);
  }

  @Test
  void processingCannotBeEditedOrConfirmedAndFailureCanBeRecovered() throws Exception {
    when(provider.extract(any(), anyString()))
        .thenAnswer(
            invocation -> {
              UUID id =
                  Store.uuid(
                      db.one(
                              "SELECT id FROM receipt WHERE owner_id=? AND status='PROCESSING'",
                              user)
                          .get("id"));
              assertThatThrownBy(() -> receipts.save(user, id, draft()))
                  .isInstanceOf(ApiException.class);
              assertThatThrownBy(() -> receipts.confirm(user, id)).isInstanceOf(ApiException.class);
              throw new IllegalStateException("secret upstream details");
            });
    var receipt =
        receipts.upload(
            user, new MockMultipartFile("file", "receipt.png", "image/png", fixture("png")));
    assertThat(receipt.get("status")).isEqualTo("FAILED");
    assertThat(receipt.get("error").toString()).doesNotContain("secret");
    UUID id = Store.uuid(receipt.get("id"));
    assertThat(db.list("SELECT id FROM expense WHERE receipt_id=?", id)).isEmpty();
    receipts.save(user, id, draft());
    receipts.confirm(user, id);
    assertThat(receipts.get(user, id).get("status")).isEqualTo("CONFIRMED");
  }

  @Test
  void invalidProviderResultNeverBecomesReviewableOrFinancial() throws Exception {
    when(provider.extract(any(), anyString())).thenReturn(null);
    var receipt =
        receipts.upload(
            user, new MockMultipartFile("file", "receipt.png", "image/png", fixture("png")));
    assertThat(receipt.get("status")).isEqualTo("FAILED");
    assertThat(db.list("SELECT id FROM expense WHERE owner_id=?", user)).isEmpty();
  }
}
