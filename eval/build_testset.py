"""성능 비교용 시험 세트(스미싱 130 + 정상 130)를 만든다.

    .venv\\Scripts\\python.exe -m eval.build_testset

- 외부 데이터: meal-bbang/Korean_message (Hugging Face, 라이선스 미표기). 리비전을 고정해 받는다.
  class 1(일상 문자)은 댓글 위주라 쓰지 않는다. class 2(피싱)는 광고·도박 스팸이 많아
  스미싱 유형 키워드로 거른다. class 3(설명 없음)은 배송 알림이라 정상 문자로 쓴다.
- known_db: 개발 DB의 악성 URL·전화번호를 넣어 직접 작성한다 (DB 읽기 전용).
- ours_normal: 은행·카드·공공기관 안내 형태의 가상 정상 문자.
- ours_smishing: 데이터셋에 없는 최근 수법을 직접 쓴 문자. 시스템을 알고 쓴 문자라 결과를 따로 본다.

결과는 eval/data/testset.jsonl (Git 제외). 시드와 리비전이 같으면 항상 같은 세트가 나온다.
"""

import csv
import json
import random
import re
import urllib.request
from pathlib import Path

from sqlalchemy import text

DATA = Path(__file__).resolve().parent / "data"
RAW = DATA / "raw" / "lgaidataset.csv"
OUT = DATA / "testset.jsonl"
REVIEW = DATA / "review.tsv"

HF_REVISION = "733664490a9a1bc985e7590f8a9bd392566e6834"
HF_URL = f"https://huggingface.co/datasets/meal-bbang/Korean_message/resolve/{HF_REVISION}/lgaidataset.csv"
SEED = 20261028

# 기관·택배 사칭, 결제·계정 확인, 인증 요구 등 스미싱 유형
SMISHING_KEYWORDS = re.compile(
    r"택배|배송|반송|주소지|운송장|결제|승인|해외|국외발신|계정|로그인|인증|본인확인|비밀번호|정지|만료|"
    r"환급|지원금|재난|과태료|범칙금|검찰|경찰|수사|청첩장|부고|명의|카드|소액|건강검진|보험료|미납|연체"
)
# 광고·도박 스팸, 구인 광고, 정상 인증번호 안내
SPAM_KEYWORDS = re.compile(
    r"\(광고\)|광고\)|무료수신거부|수신거부|토토|카지노|카지no|casino|바카라|슬롯|배팅|베팅|벳|첫충|매충|충전|먹튀|섭스|"
    r"VIP|vip|이벤트|이밴|가입머니|대출|금리|한도|주식|종목|리딩|수익|투자|노랑|노란톡|"
    r"해외기업|해외선물|해외안전|놀이터|콤프|롤링|입플|꽁|무사고|정식\s?라이센스|라이센스|톡방|카톡|"
    r"소::개|소\(개\)|찾아가세요|사용잔액|모집|가입이\s?승인|인증\s?코드는|"
    r"환급받|매주|마진|채굴|당일배송|러브캐처|회원들|스포츠|치킨|에이젼씨|해외정식|가입금|입장|"
    r"계류중|repair|l-?O-?%|lO%|인증\s?코드|로그인\s?코드|bet|볫|어코드|바이너리|겜|야망광고|잔\*여|공식기업|스폰|치퀸|고배당|가입코드|규제|폴츄",
    re.IGNORECASE,
)
# 원문자(ⓐ①)로 주소를 가린 도박 스팸
OBFUSCATED = re.compile(r"[①-⓿]")
NAME_HONORIFIC = re.compile(r"[가-힣*?]{1,4}\s?(?:고객님|회원님|님)")


# 머리말 표기만 바꿔 대량 발송한 같은 캠페인
CAMPAIGNS = {"coinone-ip": re.compile(r"해외\s?(IP|아이피)", re.IGNORECASE)}


def _near_key(text: str, length: int = 12) -> str:
    # 이름·상품명·금액만 다른 같은 틀의 문자를 하나로 본다
    for name, pattern in CAMPAIGNS.items():
        if pattern.search(text):
            return name
    return re.sub(r"[^가-힣]", "", NAME_HONORIFIC.sub("", text))[:length]

OURS_NORMAL = [
    "[우리은행] 고객님의 정기예금이 11월 5일 만기 예정입니다. 우리WON뱅킹 앱에서 확인하세요.",
    "[우리은행] 10월 급여 2,500,000원이 입금되었습니다.",
    "[우리은행] 영업점 방문 예약이 완료되었습니다. 예약일 11/2 14:00 종로지점",
    "[우리은행] 자동이체(관리비) 182,300원이 출금되었습니다.",
    "[우리은행] 정기예금 만기 안내. 자세한 내용은 https://wooribank.com 에서 확인하세요.",
    "[우리카드] 10/27 12:31 승인 15,000원 가상편의점 누적 320,000원",
    "[우리카드] 10월 이용대금 452,000원이 11/14 결제될 예정입니다.",
    "[우리카드] 해외 결제 승인 USD 12.99 가상스트리밍 누적 410,000원",
    "[가상카드] 11월 카드 명세서가 발송되었습니다. 앱에서 확인 바랍니다.",
    "[가상카드] 포인트 3,200P가 적립되었습니다.",
    "[국민건강보험] 건강검진 대상자 안내. 올해 안에 가까운 검진기관에서 받으세요.",
    "[질병관리청] 독감 예방접종 무료 접종 기간 안내. 가까운 지정 의료기관을 이용하세요.",
    "[국세청] 연말정산 간소화 서비스가 1월 15일부터 열립니다. 홈택스에서 이용하세요.",
    "[가상구청] 대형폐기물 수거 신청이 접수되었습니다. 수거일 11/3",
    "[가상주민센터] 신청하신 주민등록등본 발급이 완료되었습니다.",
    "[가상도서관] 대출하신 도서의 반납일은 11월 4일입니다.",
    "[가상병원] 10월 30일 오전 10시 진료 예약되었습니다. 변경은 앱에서 가능합니다.",
    "[가상치과] 내일 오후 3시 예약 확인 부탁드립니다.",
    "[가상약국] 처방 약 조제가 완료되었습니다. 방문 수령 바랍니다.",
    "[가상통신] 이번 달 요금 45,200원이 자동이체될 예정입니다.",
    "[가상통신] 데이터 사용량이 90%에 도달했습니다.",
    "[가상통신] 요금제 변경이 완료되었습니다. 다음 달 1일부터 적용됩니다.",
    "[가상쇼핑] 주문하신 상품 결제가 완료되었습니다. 결제금액 32,000원",
    "[가상쇼핑] 주문하신 상품이 출고되었습니다. 배송 조회는 앱에서 확인하세요.",
    "[가상쇼핑] 반품 신청이 접수되었습니다. 회수 기사님이 방문 예정입니다.",
    "[가상마트] 회원님 생일 축하 쿠폰 5,000원이 지급되었습니다. 앱에서 확인하세요.",
    "[가상항공] 10월 30일 김포-제주 탑승권이 발급되었습니다. 출발 30분 전까지 탑승구로 오세요.",
    "[가상철도] 11/1 서울→부산 승차권 예매가 완료되었습니다.",
    "[가상호텔] 11/15 체크인 예약이 확정되었습니다.",
    "[가상아파트] 엘리베이터 정기 점검으로 11/2 10~12시 운행이 중지됩니다.",
    "[가상학원] 이번 주 금요일 수업은 휴강입니다.",
    "[가상헬스장] 회원권이 11월 30일 만료됩니다. 재등록은 데스크에서 가능합니다.",
    "[가상대학교] 2학기 성적 열람 기간은 12/20부터입니다.",
    "[가상보험] 보험료 52,000원이 정상 납부되었습니다.",
    "[가상증권] 주문하신 매수 체결이 완료되었습니다.",
    "[가상페이] 1,000원이 충전되었습니다.",
    "엄마 오늘 늦을 것 같아 저녁 먼저 먹어",
    "내일 3시에 카페에서 보자",
    "결혼식 와줘서 고마워! 사진 정리되면 보내줄게",
    "회의 자료 메일로 보냈어요. 확인 부탁드립니다.",
    # 스미싱과 주제가 겹치는 정상 안내 (링크·대표번호 포함)
    "[우리은행] 고객님의 인터넷뱅킹 비밀번호가 변경되었습니다. 본인이 아니면 우리WON뱅킹 앱에서 확인하세요.",
    "[우리은행] 새 기기에서 우리WON뱅킹 로그인이 확인되었습니다. 본인이 아니면 앱에서 기기를 해제하세요.",
    "[우리은행] 고객님의 OTP 유효기간이 12월 31일 만료됩니다. 가까운 영업점을 방문해 주세요.",
    "[우리은행] 전세자금대출 이자 312,000원이 11/10 출금 예정입니다.",
    "[우리카드] 신청하신 카드가 발급되어 등기로 발송되었습니다. 카드 수령 후 앱에서 등록하세요.",
    "[우리카드] 카드 유효기간 만료로 새 카드가 발급되었습니다. 우리카드 앱에서 사용 등록하세요.",
    "[우리카드] 11월 결제일 변경 신청이 완료되었습니다.",
    "[우리카드] 온라인 결제 12,900원이 취소되었습니다.",
    "[가상카드] 본인 확인을 위한 인증번호 [482913]를 입력해 주세요. 타인에게 알려주지 마세요.",
    "[가상은행] 인증번호 [739201] 입니다. 앱 화면에 입력해 주세요.",
    "[CJ대한통운] 고객님의 상품이 오늘 14~18시 배송 예정입니다. 배송 조회는 CJ대한통운 앱에서 가능합니다.",
    "[우체국택배] 오늘 배달 예정입니다. 부재 시 경비실에 맡기겠습니다.",
    "[한진택배] 상품이 배송 완료되었습니다. 문 앞을 확인해 주세요.",
    "[가상쇼핑] 주문하신 상품이 품절되어 결제가 자동 취소되었습니다. 환불은 3영업일 내 처리됩니다.",
    "[가상쇼핑] 해외직구 상품이 통관 완료되어 국내 배송이 시작됩니다.",
    "[국민건강보험] 11월분 건강보험료 98,700원이 자동이체될 예정입니다.",
    "[국민연금] 연금 수령액이 25일 입금될 예정입니다.",
    "[가상구청] 재산세 2기분 납부 기간은 9월 16일부터 30일까지입니다. 위택스에서 납부하세요.",
    "[경찰청] 운전면허 적성검사 기간이 다가왔습니다. 가까운 운전면허시험장을 방문해 주세요.",
    "[가상시청] 민원 신청하신 서류가 발급 완료되었습니다. 정부24에서 확인하세요.",
    "[가상선관위] 투표소 위치는 주민센터 2층입니다. 신분증을 지참해 주세요.",
    "[가상통신] 휴대폰 할부금 납부가 완료되었습니다.",
    "[가상통신] 번호이동 개통이 완료되었습니다. 기존 유심은 폐기해 주세요.",
    "[가상렌터카] 예약하신 차량 인수 시간은 11/3 09:00입니다.",
    "[가상영화관] 예매가 완료되었습니다. 상영관 5관 G열 7번",
    "[가상중고마켓] 거래 후기가 등록되었습니다.",
    "아빠 나 오늘 학원 끝나고 친구랑 도서관 갔다 갈게",
    "형 이번 주말에 본가 내려가? 같이 가자",
    "팀장님 오늘 회의 2시로 변경됐습니다.",
    "택배 경비실에 맡겨놨어요. 퇴근길에 찾아가세요.",
    # 30건 추가: 최신 스미싱 주제와 겹치는 정상 안내
    "[한국도로공사] 하이패스 통행료 12,400원이 등록 카드로 정상 결제되었습니다.",
    "[가상구청] 모바일 부고: 가상구청장 부친상 안내. 빈소는 가상병원 장례식장 3호실입니다.",
    "[가상중고마켓] 거래가 완료되었습니다. 판매 대금은 내일 정산됩니다.",
    "[우리은행] 해외 로그인 차단 서비스가 설정되었습니다.",
    "[우리카드] 카드 분실 신고가 접수되었습니다. 재발급은 우리카드 앱에서 신청하세요.",
    "[가상통신] 고객님의 휴대폰 보험 가입이 완료되었습니다.",
    "[가상통신] 단말기 할인 약정이 11월 30일 종료됩니다. 자세한 내용은 매장에 문의하세요.",
    "[가상호텔] 예약하신 객실이 정상 결제되었습니다. 체크인은 15시부터입니다.",
    "[가상항공] 기상 악화로 11/3 출발편이 1시간 지연됩니다.",
    "[가상백화점] 구매하신 상품의 교환 접수가 완료되었습니다.",
    "[가상앱스토어] 구독이 갱신되었습니다. 결제 금액 9,900원",
    "[가상쇼핑] 회원님의 등급이 골드로 변경되었습니다.",
    "[가상주민센터] 긴급재난지원금 지급이 완료되었습니다. 등록 카드로 사용하세요.",
    "[국세청] 종합소득세 환급금이 신고 계좌로 입금되었습니다.",
    "[가상시청] 주정차 위반 과태료가 정상 납부되었습니다.",
    "[가상경찰서] 분실물 습득 신고가 접수되었습니다. 신분증 지참 후 방문 바랍니다.",
    "[가상법원] 전자소송 사건 문서가 송달되었습니다. 전자소송 홈페이지에서 확인하세요.",
    "[가상우체국] 등기우편이 도착했습니다. 부재 시 우체국에서 보관합니다.",
    "[가상대학병원] 건강검진 결과가 나왔습니다. 병원 앱에서 확인 가능합니다.",
    "[가상약국] 처방전 접수가 완료되었습니다. 10분 후 수령 가능합니다.",
    "[가상보험] 실손보험금 35,000원이 지급되었습니다.",
    "[가상증권] 배당금 12,300원이 입금되었습니다.",
    "[가상페이] 송금 50,000원이 완료되었습니다.",
    "[가상카드] 해외 결제 차단 서비스가 해제되었습니다.",
    "[가상관리사무소] 수도 검침이 내일 진행됩니다.",
    "[가상동창회] 모임은 11월 9일 저녁 7시 가상식당입니다.",
    "누나 나 이번 달 용돈 잘 받았어 고마워",
    "여보 마트에서 우유 좀 사와",
    "선배님 결혼 축하드려요! 청첩장 잘 받았습니다.",
    "친구야 생일 축하해! 저녁에 전화할게",
]

# 데이터셋에 없는 최근 수법. 링크·번호는 DB에 없는 가상 값이라 "신종 문자" 시험이 된다.
# 수법 카드 예시 문장을 옮기지 않고 새로 썼다.
OURS_SMISHING = [
    "[부고] 故 김OO님께서 별세하셨기에 삼가 알려드립니다. 장례식장 안내: http://bugo-notice.top/k3",
    "[모바일부고장] 부친상 알림. 조문 및 장지 확인 http://m-bugo.xyz/9a",
    "[한국도로공사] 하이패스 통행료 미납 3건. 오늘까지 미납 시 가산금 부과. 납부 http://ex-pay.click/n2",
    "[중고마켓 안전결제] 구매자가 결제를 완료했습니다. 판매 대금 수령을 위해 계좌 인증을 해주세요 http://safe-pay-market.shop/a",
    "판매자님 안전결제로 보냈어요 링크에서 확인하고 송금 받으시면 돼요 http://trade-secure.site/p",
    "[가상카드] 고객님 신청 카드가 내일 배송됩니다. 신청하지 않으셨다면 고객센터 070-4821-3390으로 즉시 연락 바랍니다.",
    "[카드발급센터] 본인 미신청 카드 발급 건이 확인되었습니다. 명의도용 신고 접수: 070-5512-0921",
    "[금융감독원] 고객님 명의로 대출 신청이 접수되었습니다. 본인이 아닐 경우 02-3355-1180으로 연락하세요.",
    "[서울중앙지검] 귀하 명의 계좌가 범죄에 이용되어 조사 예정입니다. 담당 수사관 010-2948-1173 연락 바람",
    "[국민건강보험] 미환급금 184,300원이 있습니다. 오늘 마감. 신청 http://nhis-refund.top/go",
    "[국세청] 미수령 환급금 안내. 본인 확인 후 즉시 수령하세요 http://hometax-refund.xyz/r",
    "[정부24] 민생회복 지원금 신청 대상자입니다. 기한 내 미신청 시 소멸됩니다 http://gov24-support.click/s",
    "[가상통신] 고객님 휴대폰 공시지원금 추가 지급 대상입니다. 기기변경 신청 http://phone-benefit.shop/m",
    "[이벤트 당첨] 축하합니다! 최신 스마트폰 경품에 당첨되었습니다. 배송비 3,000원 결제 후 수령 http://lucky-event.top/w",
    "[가상쇼핑] 고객님 계정에서 이상 결제가 감지되었습니다. 결제 취소는 앱 설치 후 진행 http://shop-secure.apk.site",
    "[크롬 업데이트] 보안 업데이트가 필요합니다. 설치하지 않으면 은행 앱이 차단됩니다 http://chrome-update.app-down.xyz",
    "[PDF 뷰어] 수신한 문서를 열려면 전용 뷰어를 설치하세요 http://doc-viewer.top/install",
    "[가상호텔] 예약 확인을 위해 결제 정보 재인증이 필요합니다. 24시간 내 미인증 시 취소 http://hotel-reconfirm.site/b",
    "[가상은행] 고객님 계정이 휴면 처리될 예정입니다. 유지하려면 본인인증 http://bank-keep.top/id",
    "[네이버] 고객님 계정이 비정상 로그인으로 일시 제한되었습니다. 해제 http://naver-unlock.xyz/c",
    "[개인정보 유출 보상] 해킹 사고 피해 고객 보상금 신청 안내. 대상 여부 조회 http://leak-refund.click/q",
    "[질병관리청] 신종 감염병 무료 검사 대상입니다. 예약 http://kdca-test.top/v",
    "엄마 나 폰 깨져서 친구 폰으로 연락해 급하게 결제할 게 있는데 엄마 카드 앞뒤 사진 좀 보내줄 수 있어?",
    "아빠 나 휴대폰 보험 처리 중이라 이 번호로만 연락돼 인증번호 하나만 받아서 알려줘",
    "삼촌 저 조카예요 폰이 고장나서 문자로 연락드려요 급하게 상품권 좀 부탁드려도 될까요?",
    "[모바일 청첩장] 저희 두 사람 결혼합니다. 오시는 길 확인 http://wedding-card.shop/j",
    "[택배] 고객님 물품 통관 보류. 개인통관고유부호 확인 필요 http://customs-check.top/u",
    "[우체국] 등기 반송 예정. 수취인 정보 확인 바랍니다 http://epost-check.xyz/d",
    "[교통민원24] 쓰레기 무단투기 과태료 고지서가 발송되었습니다 http://efine-notice.click/t",
    "[가상페이] 해외 결제 1,280,000원 승인. 본인 아닐 경우 즉시 취소 요청 070-7712-5506",
]

# 검증 세트 정상 문자 (1차 결과를 본 뒤 판정 규칙을 고쳤으므로, 1차와 겹치지 않게 새로 썼다).
# 실제 받은 편지함처럼 링크 없는 안내·공식/비공식 링크·대표번호·개인 대화를 섞었다.
VALIDATION_NORMAL = [
    # 발신 표기만 있고 링크·번호 없는 안내
    "[우리은행] 11월 적금 자동이체 300,000원이 정상 처리되었습니다.",
    "[우리은행] 외화 환전 신청이 완료되었습니다. 수령 지점: 강남역지점",
    "[우리은행] 고객님의 체크카드 결제 8,900원이 승인되었습니다.",
    "[우리은행] 이번 달 우대금리 조건을 충족하셨습니다.",
    "[우리카드] 11/02 18:44 승인 23,400원 가상식당 일시불",
    "[우리카드] 정기결제 13,900원이 승인되었습니다. 가상음악",
    "[우리카드] 이번 달 포인트 1,250P가 소멸 예정입니다.",
    "[가상은행] 예금 이자 4,120원이 지급되었습니다.",
    "[가상은행] 계좌 개설이 완료되었습니다.",
    "[가상카드] 가족카드 발급 신청이 접수되었습니다.",
    "[가상카드] 할부 3개월 승인 360,000원 가상전자",
    "[가상증권] 11월 투자 설명회 일정 안내드립니다.",
    "[가상보험] 자동차보험 갱신이 완료되었습니다.",
    "[가상생명] 보험금 청구가 접수되었습니다. 심사 후 안내드리겠습니다.",
    "[국민연금공단] 가입내역 안내서가 발송되었습니다.",
    "[건강보험공단] 이번 달 보험료 납부가 확인되었습니다.",
    "[국세청] 부가가치세 신고 기간은 1월 25일까지입니다.",
    "[행정안전부] 주민등록증 재발급 신청이 접수되었습니다.",
    "[가상시청] 대설주의보 발효. 외출 시 안전에 유의하세요.",
    "[가상구청] 이번 주 토요일 재활용품 수거 시간이 변경됩니다.",
    "[가상교육청] 내일은 재량휴업일입니다.",
    "[가상초등학교] 현장체험학습 동의서를 금요일까지 제출해 주세요.",
    "[가상유치원] 오늘 오후 4시 하원 차량이 10분 늦게 출발합니다.",
    "[가상병원] 검사 결과 상담 예약이 11/7 오전 9시로 잡혔습니다.",
    "[가상한의원] 내일 진료는 오후 2시부터 시작합니다.",
    "[가상동물병원] 예방접종 예정일이 다가왔습니다.",
    "[가상헬스장] 이번 주 일요일은 휴관입니다.",
    "[가상도서관] 예약하신 도서가 도착했습니다. 3일 내 대출해 주세요.",
    "[가상문화센터] 수강 신청하신 강좌가 확정되었습니다.",
    "[가상마트] 주문하신 장보기 상품이 오늘 저녁 배송됩니다.",
    "[가상편의점] 택배 접수가 완료되었습니다.",
    "[가상세탁소] 맡기신 세탁물이 완료되었습니다.",
    "[가상미용실] 내일 오전 11시 예약 확인 부탁드립니다.",
    "[가상주차장] 정기권이 11월 30일 만료됩니다.",
    "[가상관리사무소] 이번 달 관리비는 214,600원입니다.",
    "[가상도시가스] 정기 안전점검이 11/9 진행됩니다.",
    "[가상전력] 이번 달 전기요금 58,300원이 청구되었습니다.",
    "[가상수도사업소] 수도요금 고지서가 발송되었습니다.",
    "[가상통신] 고객님의 약정이 다음 달 만료됩니다.",
    "[가상통신] 해외 로밍 요금제가 개통되었습니다.",
    # 링크가 있는 안내 (공식 DB에 있는 도메인과 없는 도메인)
    "[우리은행] 연말정산 서류는 https://wooribank.com 에서 발급받으실 수 있습니다.",
    "[우리은행] 금융사기 예방 안내: 의심 문자는 https://wooribank.com 고객센터 메뉴에서 확인하세요.",
    "[우리카드] 11월 이벤트 안내 https://wooricard.com",
    "[우리금융] 주주총회 안내 https://woorifg.com",
    "[가상쇼핑] 주문 상세 내역 https://shop.example/order/1023",
    "[가상쇼핑] 리뷰 작성하고 적립금 받으세요 https://shop.example/review",
    "[가상서점] 주문하신 도서가 발송되었습니다 https://books.example/track",
    "[가상항공] 모바일 탑승권 https://air.example/boarding",
    "[가상여행] 예약 확인서 https://travel.example/booking/88",
    "[가상공연] 티켓 예매 완료 https://ticket.example/my",
    "[가상설문] 서비스 만족도 조사에 참여해 주세요 https://survey.example/s1",
    "[가상학교] 가정통신문 확인 https://school.example/notice/12",
    "[가상회사] 이번 주 사내 공지 https://intra.example/notice",
    "[가상구청] 주민 참여 예산 공모 안내 https://gu.example/budget",
    "[가상시청] 버스 노선 변경 안내 https://city.example/bus",
    # 대표번호가 적힌 안내
    "[가상카드] 카드 분실 신고 접수가 완료되었습니다. 문의 1588-0000",
    "[가상은행] 영업점 이전 안내. 문의는 대표번호 1599-0000으로 해주세요.",
    "[가상통신] 요금 문의는 국번 없이 114로 연락 주세요.",
    "[가상택배] 기사님이 오후에 방문 예정입니다. 문의 1588-1255",
    "[가상병원] 예약 변경은 02-0000-0000 으로 연락 바랍니다.",
    "[가상보험] 상담 예약이 완료되었습니다. 상담사 연락처 1577-0000",
    "[가상아파트] 엘리베이터 고장 신고는 관리사무소 031-000-0000",
    "[가상렌터카] 반납 장소 변경 문의 1644-0000",
    "[가상가스] 점검 일정 변경은 1544-0000으로 연락 주세요.",
    "[가상학원] 상담은 02-000-0000으로 연락 주세요.",
    # 개인 대화
    "엄마 오늘 저녁 뭐 먹어?",
    "아빠 나 시험 끝났어 이제 집 가는 중",
    "형 주말에 축구 볼래?",
    "누나 생일 선물 뭐 갖고 싶어?",
    "여보 퇴근길에 빵 좀 사올게",
    "자기야 오늘 늦어? 먼저 잘게",
    "친구야 내일 몇 시에 만날까?",
    "선배 오늘 회식 장소 어디예요?",
    "팀장님 보고서 초안 공유드렸습니다.",
    "과장님 내일 오전 반차 쓰겠습니다.",
    "삼촌 명절에 뵐게요!",
    "이모 김장 언제 해요?",
    "할머니 감기 괜찮으세요?",
    "동생아 충전기 어디 뒀어?",
    "오늘 동아리 모임 7시로 바뀜",
    "단톡 공지: 다음 주 스터디 휴강",
    "택배 왔길래 문 앞에 들여놨어",
    "주차 자리 비었어 지금 와",
    "점심 같이 먹을래?",
    "사진 잘 받았어 고마워",
    "비 온대 우산 챙겨",
    "회의록 메일로 보냈습니다",
    "내일 등산 취소야 날씨 안 좋대",
    "아까 빌린 돈 저녁에 보내줄게",
    "엄마 나 지금 버스 탔어",
    "결혼 축하해! 행복하게 살아",
    "조문은 내일 오후에 같이 가자",
    "생일 축하해 케이크 사갈게",
    "다음 달 여행 숙소 예약했어",
    "강아지 산책 시켜줘서 고마워",
    "이번 주 금요일 휴가야",
    "고객님 요청하신 견적서 메일로 보내드렸습니다",
    "안녕하세요 부동산입니다 계약서 사본 확인 부탁드립니다",
    "택시 잡았어 10분 뒤 도착",
    "오늘 수업 녹화본 올라왔어",
]

# 개발 DB의 악성 값을 끼워 넣는 틀. {url}·{phone} 중 하나만 쓴다.
KNOWN_TEMPLATES = [
    "[택배] 주소지 불일치로 반송 예정입니다. 확인: {url}",
    "[국외발신] 고객님 계정이 해외에서 로그인되었습니다. 본인이 아니면 {url}",
    "[교통민원] 신호위반 과태료 미납 안내. 확인 {url}",
    "[정부지원금] 오늘 마감. 신청하기 {url}",
    "[모바일 청첩장] 저희 결혼합니다. 참석 부탁드려요 {url}",
    "[가상은행] 고객님 계좌가 정지되었습니다. 해제 문의 {phone}",
    "[가상카드] 해외 결제 승인 980,000원. 본인 아니면 {phone} 연락",
    "[검찰청] 명의 도용 사건 관련 확인이 필요합니다. {phone}로 연락 바랍니다.",
    "[택배] 상품 보관 중. 수령 문의 {phone}",
    "[건강보험] 환급금 조회 안내 {url}",
]


def _download() -> None:
    if RAW.exists():
        return
    RAW.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(HF_URL, timeout=60) as response:
        RAW.write_bytes(response.read())


def _load() -> dict[str, list[tuple[str, str]]]:
    rows = csv.DictReader(RAW.read_text(encoding="utf-8-sig").splitlines())
    by: dict[str, list[tuple[str, str]]] = {}
    seen: set[str] = set()
    for row in rows:
        content = (row["content"] or "").strip()
        if not content or content in seen:
            continue
        seen.add(content)
        by.setdefault(row["class"], []).append((row["index"], content))
    return by


def _unique_template(
    rows: list[tuple[str, str]], per_template: int = 1, key_length: int = 12
) -> list[tuple[str, str]]:
    kept: dict[str, list[tuple[str, str]]] = {}
    for idx, t in rows:
        group = kept.setdefault(_near_key(t, key_length), [])
        if len(group) < per_template:
            group.append((idx, t))
    return [row for group in kept.values() for row in group]


def _format_phone(digits: str) -> str:
    head = 2 if digits.startswith("02") else 3
    return f"{digits[:head]}-{digits[head:-4]}-{digits[-4:]}"


def _known_db(rng: random.Random) -> list[dict]:
    from app.db.session import get_session_factory

    with get_session_factory()() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        urls = list(db.execute(text(
            "SELECT value_normalized FROM indicators WHERE type = 'url' ORDER BY id LIMIT 500"
        )).scalars())
        phones = list(db.execute(text(
            "SELECT value_normalized FROM indicators WHERE type = 'phone' ORDER BY id"
        )).scalars())
        db.rollback()
    items = []
    for n, template in enumerate(KNOWN_TEMPLATES, 1):
        message = template.format(url=rng.choice(urls), phone=_format_phone(rng.choice(phones)))
        items.append({"id": f"K-{n:03}", "text": message, "label": "smishing", "group": "known_db",
                      "source": "ours+dev-db"})
    return items


def build() -> list[dict]:
    _download()
    rng = random.Random(SEED)
    by = _load()

    smishing_pool = _unique_template(per_template=1, rows=[
        (idx, t) for idx, t in by["2"]
        if SMISHING_KEYWORDS.search(t) and not SPAM_KEYWORDS.search(t) and not OBFUSCATED.search(t)
        and 10 <= len(t) <= 300
    ])
    # class 3은 틀 몇 개에 이름·상품명만 바꾼 문자라 앞부분(업체명)이 같은 틀은 최대 4건만 쓴다
    delivery_pool = _unique_template(by["3"], per_template=4, key_length=6)
    delivery_count = min(len(delivery_pool), 30)

    items = _known_db(rng)
    for n, (idx, t) in enumerate(rng.sample(smishing_pool, 90), 1):
        items.append({"id": f"S-{n:03}", "text": t, "label": "smishing", "group": "dataset_smishing",
                      "source": f"hf:meal-bbang/Korean_message@{HF_REVISION[:7]}#index={idx}"})
    for n, (idx, t) in enumerate(rng.sample(delivery_pool, delivery_count), 1):
        items.append({"id": f"D-{n:03}", "text": t, "label": "normal", "group": "dataset_delivery",
                      "source": f"hf:meal-bbang/Korean_message@{HF_REVISION[:7]}#index={idx}"})
    for n, t in enumerate(OURS_NORMAL, 1):
        items.append({"id": f"N-{n:03}", "text": t, "label": "normal", "group": "ours_normal", "source": "ours"})
    for n, t in enumerate(OURS_SMISHING, 1):
        items.append({"id": f"M-{n:03}", "text": t, "label": "smishing", "group": "ours_smishing", "source": "ours"})

    print(f"스미싱 후보 {len(smishing_pool)}건 중 90건, 배송 알림 {len(delivery_pool)}건 중 {delivery_count}건 추출")
    return items


VALIDATION_OUT = DATA / "validation.jsonl"


def build_validation() -> list[dict]:
    """1차 시험 세트에 쓰지 않은 데이터셋 스미싱 + 새로 쓴 정상 문자."""
    used = {json.loads(line)["source"] for line in OUT.read_text(encoding="utf-8").splitlines() if line}
    by = _load()
    pool = _unique_template(per_template=1, rows=[
        (idx, t) for idx, t in by["2"]
        if SMISHING_KEYWORDS.search(t) and not SPAM_KEYWORDS.search(t) and not OBFUSCATED.search(t)
        and 10 <= len(t) <= 300
    ])
    items = []
    for idx, t in pool:
        source = f"hf:meal-bbang/Korean_message@{HF_REVISION[:7]}#index={idx}"
        if source not in used:
            items.append({"id": f"VS-{len(items) + 1:03}", "text": t, "label": "smishing",
                          "group": "dataset_smishing", "source": source})
    for n, t in enumerate(VALIDATION_NORMAL, 1):
        items.append({"id": f"VN-{n:03}", "text": t, "label": "normal", "group": "ours_normal_v2", "source": "ours"})
    return items


def main() -> None:
    import sys

    if "--validation" in sys.argv:
        items = build_validation()
        VALIDATION_OUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
        print(f"저장: {VALIDATION_OUT} ({len(items)}건)")
        return
    items = build()
    OUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    # 사람이 훑어볼 표. 원문 대신 마스킹한 문자를 둔다.
    from app.services.masking import mask_text

    REVIEW.write_text(
        "id\tgroup\tlabel\ttext(masked)\n"
        + "".join(f"{i['id']}\t{i['group']}\t{i['label']}\t{mask_text(i['text']).replace(chr(10), ' ')}\n" for i in items),
        encoding="utf-8-sig",
    )
    counts: dict[str, int] = {}
    for i in items:
        counts[i["group"]] = counts.get(i["group"], 0) + 1
    print(f"저장: {OUT} ({len(items)}건) {counts}")
    print(f"검토용 표: {REVIEW}")


if __name__ == "__main__":
    main()
