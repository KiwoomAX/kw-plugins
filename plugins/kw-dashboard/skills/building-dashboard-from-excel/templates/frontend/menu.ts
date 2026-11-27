/* 사이드바 메뉴 한 줄. 대시보드 템플릿의 routes.tsx 가 src/features/<기능>/menu.ts 를 모아 메뉴를 만든다.
   복사한 뒤 <화면 이름> 과 <기능> 두 곳만 바꾼다. */
import { createElement } from 'react';
import type { FeatureMenu } from '../../feature-menu';
import ExcelFeaturePage from './ExcelFeaturePage';

const TITLE = '<화면 이름>';

const menu: FeatureMenu = { name: TITLE, page: () => createElement(ExcelFeaturePage, { api: '/api/<기능>', title: TITLE }) };
export default menu;
