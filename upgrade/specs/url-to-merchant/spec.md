# Milestone 4 — URL to Merchant Center

Chains Milestones 1 to 3 into one automated run: given the URL of a garment photo
and the fields only the brand knows, the system downloads the image, attributes
it, builds and validates the Merchant Center row, uploads it, and waits for
Google's verdict. This replaces the former ads-optimization milestone: creating
a campaign and measuring it requires paying for ads.

## ADDED Requirements

### Requirement: Brand data check
The system SHALL check the brand's required fields before downloading the image.

#### Scenario: Missing brand field fails before download
- **IF** a required brand field (price, availability, link, brand, condition) is
  missing
- **THEN** the system SHALL abort with an error naming the field and SHALL NOT
  download the image
- **TEST** `test_pipeline_missing_business_field_fails_before_download`

### Requirement: Download and attribution
The system SHALL download the image from the given URL and attribute it with
Milestone 1.

#### Scenario: Attribute the image at the URL (Mocked)
- **WHEN** an image URL and the brand fields are given
- **THEN** the system SHALL run Milestone 1 on that URL and build a Merchant
  Center product with the inferred fields and `image_link` set to the URL
- **TEST** `test_pipeline_enriches_from_image_url`

#### Scenario: Download failure stops the run (Mocked)
- **IF** the image cannot be downloaded
- **THEN** the system SHALL stop with stage `download_failed` and upload nothing
- **TEST** `test_pipeline_stops_when_download_fails`

### Requirement: Validation gate
The system SHALL upload a product only if it passes Milestone 2 validation.

#### Scenario: Invalid product is not uploaded (Mocked)
- **IF** the built product fails validation
- **THEN** the system SHALL stop with stage `invalid`, return the validation
  reasons, and upload nothing
- **TEST** `test_pipeline_skips_upload_when_invalid`

### Requirement: Upload to Merchant Center
The system SHALL upload the valid product with Milestone 3.

#### Scenario: Valid product is uploaded (Mocked)
- **WHEN** the product passes validation
- **THEN** the system SHALL upload it once and end with stage `uploaded`
- **TEST** `test_pipeline_uploads_valid_product`

#### Scenario: Upload error is reported (Mocked)
- **IF** Merchant Center rejects the upload
- **THEN** the system SHALL end with stage `upload_failed` and return the API error
- **TEST** `test_pipeline_reports_upload_error`

#### Scenario: Same image keeps the same product ID
- **WHEN** the pipeline runs twice on the same URL without an explicit ID
- **THEN** the system SHALL use the same offer ID both times, so the second run
  updates the product instead of duplicating it
- **TEST** `test_product_id_is_stable_for_same_url`

### Requirement: Dry run
The system SHALL support a dry-run mode that builds and validates the product
without uploading it.

#### Scenario: Dry run uploads nothing (Mocked)
- **WHEN** the pipeline runs in dry-run mode
- **THEN** the system SHALL return the built product with stage `dry_run` and make
  no Merchant API call
- **TEST** `test_pipeline_dry_run_makes_no_upload`

### Requirement: Google's verdict
The system SHALL poll Merchant Center until Google approves or disapproves the
uploaded product, up to a time limit.

#### Scenario: Wait until approved (Mocked)
- **WHEN** Merchant Center reports `pending` and later `approved`
- **THEN** the system SHALL keep polling and return the `approved` status
- **TEST** `test_wait_for_status_returns_verdict`

#### Scenario: Give up after the time limit (Mocked)
- **IF** the product is still `pending` when the time limit runs out
- **THEN** the system SHALL stop polling and return the `pending` status
- **TEST** `test_wait_for_status_gives_up_after_timeout`

## Tests

- `test_pipeline_missing_business_field_fails_before_download`
- `test_pipeline_enriches_from_image_url`
- `test_pipeline_stops_when_download_fails`
- `test_pipeline_skips_upload_when_invalid`
- `test_pipeline_uploads_valid_product`
- `test_pipeline_reports_upload_error`
- `test_product_id_is_stable_for_same_url`
- `test_pipeline_dry_run_makes_no_upload`
- `test_wait_for_status_returns_verdict`
- `test_wait_for_status_gives_up_after_timeout`
