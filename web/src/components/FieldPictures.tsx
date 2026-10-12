/* The pictures waiting above the field, in the stack MovingStack hosts: the one under the pointer lifts, a press picks it
   and gives it a cross to take it off; a press leaves the keys in the field. */
import type { MouseEvent } from 'react'
import { AppIcon } from './AppIcon'
import { PICTURE_HEIGHT, pictures, removePicture, stackWidth, tapPicture, tileWidth } from '../lib/reportPictures'
import { cx, fallthrough, sx } from '../bind'
import { tracked } from '../tracked'
import './fieldPictures.css'

const keepFocus = (event: MouseEvent) => event.preventDefault()

export const FieldPictures = tracked(function FieldPictures(attrs: Record<string, unknown>) {
  const count = pictures.list.length
  const own = {
    className: cx('field-pictures', { 'is-sending': pictures.sending }),
    style: sx({ '--stack': `${stackWidth(pictures.list)}px`, '--n': count, '--h': `${PICTURE_HEIGHT}px` }),
    'data-role': 'field-pictures',
  }
  return (
    <div {...fallthrough(own, attrs)}>
      {pictures.list.map((picture, index) => {
        const picked = pictures.picked === picture.id
        return (
          <div key={picture.id} className={cx('field-pictures__item', { 'is-picked': picked })}
            style={sx({ '--w': `${tileWidth(picture)}px` })} data-role="field-picture">
            <button
              type="button"
              className="field-pictures__hit"
              aria-label={`Picture ${index + 1} of ${count}, ${picture.name}`}
              aria-pressed={picked}
              onMouseDown={keepFocus}
              onClick={(event) => {
                event.stopPropagation()
                tapPicture(picture.id)
              }}
            ></button>
            <span className="field-pictures__pic" aria-hidden="true"><img src={picture.url} alt="" draggable={false} decoding="async" /></span>
            <button
              type="button"
              className="field-pictures__remove"
              aria-label={`Take picture ${index + 1} off`}
              tabIndex={picked ? 0 : -1}
              data-role="field-picture-remove"
              onMouseDown={keepFocus}
              onClick={(event) => {
                event.stopPropagation()
                removePicture(picture.id)
              }}
            ><AppIcon name="x" size={12} stroke={2.8} /></button>
          </div>
        )
      })}
    </div>
  )
})
