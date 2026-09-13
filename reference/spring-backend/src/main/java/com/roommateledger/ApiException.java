package com.roommateledger;

import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

public class ApiException extends RuntimeException {
  final int status;
  final String code;

  public ApiException(int status, String code, String message) {
    super(message);
    this.status = status;
    this.code = code;
  }

  public static ApiException invalid(String message) {
    return new ApiException(400, "VALIDATION_ERROR", message);
  }

  public static ApiException forbidden() {
    return new ApiException(403, "FORBIDDEN", "You do not have access to this record.");
  }

  public static ApiException missing() {
    return new ApiException(404, "NOT_FOUND", "Record not found.");
  }
}

@RestControllerAdvice
class ErrorHandler {
  @ExceptionHandler(Exception.class)
  ResponseEntity<?> unexpected(Exception e) {
    String reference = java.util.UUID.randomUUID().toString();
    org.slf4j.LoggerFactory.getLogger(ErrorHandler.class)
        .error(
            "request_failed reference={} exception_type={}",
            reference,
            e.getClass().getSimpleName());
    return ResponseEntity.status(500)
        .body(
            Map.of(
                "code",
                "INTERNAL_ERROR",
                "message",
                "Something went wrong. Retry or contact support with reference " + reference));
  }

  @ExceptionHandler(ApiException.class)
  ResponseEntity<?> domain(ApiException e) {
    return ResponseEntity.status(e.status).body(Map.of("code", e.code, "message", e.getMessage()));
  }

  @ExceptionHandler({
    MethodArgumentNotValidException.class,
    IllegalArgumentException.class,
    java.time.DateTimeException.class,
    org.springframework.web.multipart.support.MissingServletRequestPartException.class,
    org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class,
    org.springframework.http.converter.HttpMessageNotReadableException.class
  })
  ResponseEntity<?> validation(Exception e) {
    return ResponseEntity.badRequest()
        .body(
            Map.of(
                "code",
                "VALIDATION_ERROR",
                "message",
                "Check the required fields, dates and amounts."));
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  ResponseEntity<?> conflict(Exception e) {
    return ResponseEntity.status(409)
        .body(
            Map.of(
                "code",
                "CONFLICT",
                "message",
                "This record conflicts with existing data. Refresh and try again."));
  }

  @ExceptionHandler(MaxUploadSizeExceededException.class)
  ResponseEntity<?> upload(Exception e) {
    return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
        .body(
            Map.of("code", "FILE_TOO_LARGE", "message", "Use a receipt image smaller than 8 MB."));
  }
}
